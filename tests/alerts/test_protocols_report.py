"""Tests for the scheduled Telegram protocols report formatter."""
from __future__ import annotations

import pytest

from stake_watch.alerts.protocols_report import (
    _best_apy,
    _format_tvl,
    format_protocols_report,
)


# ---------- _format_tvl ----------

@pytest.mark.parametrize("v,expected", [
    (500, "$500"),
    (2_400, "$2K"),
    (1_200_000, "$1.2M"),
    (3_400_000_000, "$3.40B"),
])
def test_format_tvl_scales(v, expected):
    assert _format_tvl(v) == expected


# ---------- _best_apy ----------

def test_best_apy_picks_max_across_chains_and_assets():
    r = {"chains_breakdown": [
        {"chain": "ETH", "by_asset": {"USDC": {"apy": 4.5, "tvl_usd": 1}}},
        {"chain": "BASE", "by_asset": {"USDC": {"apy": 6.1, "tvl_usd": 1},
                                         "USDT": {"apy": 7.2, "tvl_usd": 1}}},
    ]}
    assert _best_apy(r) == 7.2


def test_best_apy_falls_back_to_live_apy_when_no_chains():
    assert _best_apy({"chains_breakdown": [], "live_apy": 3.14}) == 3.14


def test_best_apy_none_when_no_data():
    assert _best_apy({"chains_breakdown": []}) is None


# ---------- format_protocols_report ----------

def test_format_empty_rows_yields_placeholder():
    text = format_protocols_report([])
    assert "暂无数据" in text


def test_format_filters_disabled_protocols():
    rows = [
        {"name": "alive", "chain": "base", "enabled": True,
         "chains_breakdown": [{"chain": "BASE", "by_asset": {"USDC":
            {"apy": 5.0, "tvl_usd": 1_000_000}}}]},
        {"name": "dead", "chain": "ethereum", "enabled": False,
         "chains_breakdown": [{"chain": "ETH", "by_asset": {"USDC":
            {"apy": 9.0, "tvl_usd": 99_000_000}}}]},
    ]
    text = format_protocols_report(rows)
    assert "alive" in text
    assert "dead" not in text
    assert "共 1 个协议" in text


def test_format_renders_usdc_and_usdt_lines():
    rows = [{"name": "aave_v3_base", "chain": "base", "enabled": True,
             "chains_breakdown": [{"chain": "BASE", "by_asset": {
                 "USDC": {"apy": 4.50, "tvl_usd": 175_000_000},
                 "USDT": {"apy": 5.20, "tvl_usd": 25_000_000},
             }}]}]
    text = format_protocols_report(rows)
    assert "aave_v3_base" in text
    assert "USDC 4.50% / $175.0M" in text
    assert "USDT 5.20% / $25.0M" in text


def test_format_sorts_by_best_apy_desc():
    rows = [
        {"name": "low", "chain": "base", "enabled": True,
         "chains_breakdown": [{"chain": "BASE", "by_asset": {
             "USDC": {"apy": 3.0, "tvl_usd": 1}}}]},
        {"name": "high", "chain": "base", "enabled": True,
         "chains_breakdown": [{"chain": "BASE", "by_asset": {
             "USDC": {"apy": 8.5, "tvl_usd": 1}}}]},
    ]
    text = format_protocols_report(rows)
    assert text.index("high") < text.index("low")


def test_format_puts_primary_chain_first():
    # `chain` and chains_breakdown[*]["chain"] are case-insensitively compared
    rows = [{"name": "fluid_usdc", "chain": "ETH", "enabled": True,
             "chains_breakdown": [
                 {"chain": "BASE", "by_asset": {"USDC": {"apy": 4.0, "tvl_usd": 1}}},
                 {"chain": "ETH",  "by_asset": {"USDC": {"apy": 5.0, "tvl_usd": 1}}},
             ]}]
    text = format_protocols_report(rows)
    assert text.index("ETH:") < text.index("BASE:")


def test_format_falls_back_to_live_apy_when_no_chains():
    rows = [{"name": "x", "chain": "ethereum", "enabled": True,
             "chains_breakdown": [],
             "live_apy": 6.66, "live_tvl_usd": 1_500_000,
             "live_pool_asset": "USDC"}]
    text = format_protocols_report(rows)
    assert "APY 6.66%" in text
    assert "TVL $1.5M" in text


def test_format_falls_back_to_dash_when_live_missing():
    rows = [{"name": "x", "chain": "base", "enabled": True,
             "chains_breakdown": [],
             "live_apy": None, "live_tvl_usd": None,
             "live_pool_asset": ""}]
    text = format_protocols_report(rows)
    assert "APY —" in text
    assert "TVL —" in text


def test_format_uses_non_usdc_usdt_asset_when_present():
    rows = [{"name": "sky_susds", "chain": "ethereum", "enabled": True,
             "chains_breakdown": [{"chain": "ETH", "by_asset": {
                 "USDS": {"apy": 4.95, "tvl_usd": 9_000_000_000}}}]}]
    text = format_protocols_report(rows)
    assert "USDS 4.95%" in text
    assert "$9.00B" in text


def test_format_includes_header_with_timestamp():
    rows = [{"name": "x", "chain": "base", "enabled": True,
             "chains_breakdown": [{"chain": "BASE", "by_asset": {
                 "USDC": {"apy": 4.0, "tvl_usd": 1}}}]}]
    text = format_protocols_report(rows, tz_offset=8)
    assert "📊 协议收益定时报告" in text
    assert "━━━━" in text
