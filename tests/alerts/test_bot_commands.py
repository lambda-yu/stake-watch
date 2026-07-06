"""Tests for the interactive Telegram command bot."""
from __future__ import annotations

from datetime import datetime, timezone

from stake_watch.alerts.bot_commands import (
    format_help,
    format_protocol_detail,
)


# ---------- format_help ----------

def test_format_help_lists_all_four_commands():
    text = format_help()
    for cmd in ("/help", "/protocols", "/compare", "/protocol <"):
        assert cmd in text, f"missing {cmd} in help output"


def _make_stats(ts: datetime | None = None):
    """Cheap stand-in — the formatter only reads .timestamp."""
    class _S:
        timestamp = ts
    return _S()


def test_format_protocol_detail_full_layout():
    protocol = {
        "name": "Aave",
        "chain": "Ethereum",
        "enabled": True,
        "safety_score": 85,
        "risk_scores": {"liquidity": 90, "smart_contract": 80, "governance": 85},
    }
    chains_breakdown = [
        {
            "chain": "Ethereum",
            "by_asset": {
                "USDC": {"apy": 4.12, "tvl_usd": 1.2e9},
                "USDT": {"apy": 3.98, "tvl_usd": 8.9e8},
            },
        },
        {
            "chain": "Base",
            "by_asset": {"USDC": {"apy": 5.20, "tvl_usd": 1.2e8}},
        },
    ]
    stats = _make_stats(datetime(2026, 7, 3, 6, 20, tzinfo=timezone.utc))

    out = format_protocol_detail(
        protocol=protocol,
        chains_breakdown=chains_breakdown,
        stats=stats,
        tz_offset=8,
    )

    assert "📋 Aave" in out
    assert "链: Ethereum" in out
    assert "状态: 启用 ✓" in out
    assert "Safety Score: 85" in out
    assert "USDC" in out and "4.12" in out and "$1.20B" in out
    assert "USDT" in out and "3.98" in out and "$890.0M" in out
    assert "Base" in out
    assert "5.20" in out and "$120.0M" in out
    assert "liquidity 90" in out
    assert "smart_contract 80" in out
    assert "governance 85" in out
    assert "2026-07-03 14:20 UTC+8" in out
    # Order semantics: USDC before USDT, primary chain (Ethereum) before Base
    assert out.index("USDC") < out.index("USDT")
    assert out.index("Ethereum") < out.index("Base")


class _Pool:
    def __init__(self, asset, supply_apy):
        self.asset = asset
        self.supply_apy = supply_apy


class _Stats:
    def __init__(self, timestamp=None, tvl_usd=None, pools=None):
        self.timestamp = timestamp
        self.tvl_usd = tvl_usd
        self.pools = pools or []


def test_format_protocol_detail_fallback_when_no_chains_breakdown():
    protocol = {"name": "Aave", "chain": "Ethereum", "enabled": True,
                "safety_score": 85, "risk_scores": None}
    stats = _Stats(
        timestamp=datetime(2026, 7, 3, 6, 20, tzinfo=timezone.utc),
        tvl_usd=1.2e9,
        pools=[_Pool("USDC", 4.12)],
    )
    out = format_protocol_detail(protocol, chains_breakdown=None,
                                 stats=stats, tz_offset=8)
    assert "各链池子" not in out
    assert "ETHEREUM USDC: APY 4.12%" in out
    assert "$1.20B" in out


def test_format_protocol_detail_omits_optional_sections_when_missing():
    protocol = {"name": "X", "chain": "Base", "enabled": False,
                "safety_score": None, "risk_scores": {}}
    out = format_protocol_detail(protocol, chains_breakdown=None,
                                 stats=None, tz_offset=8)
    assert "停用 ✗" in out
    assert "Safety Score" not in out
    assert "风险评分" not in out
    assert "最新数据" not in out


def test_format_protocol_detail_truncates_long_output():
    # Build a chains_breakdown big enough to blow past 3800 chars.
    big = [
        {"chain": f"Chain-{i}", "by_asset": {
            "USDC": {"apy": 1.23, "tvl_usd": 1e8},
            "USDT": {"apy": 4.56, "tvl_usd": 2e8},
        }}
        for i in range(200)
    ]
    protocol = {"name": "Huge", "chain": "Chain-0", "enabled": True,
                "safety_score": 50, "risk_scores": {"x": 1}}
    out = format_protocol_detail(protocol, chains_breakdown=big,
                                 stats=None, tz_offset=8)
    assert len(out) <= 3800
    assert out.endswith("...(已截断)")


def test_format_protocol_detail_accepts_row_like_object():
    class _Row:
        name = "Aave"
        chain = "Ethereum"
        enabled = True
        safety_score = 85
        risk_scores = None
    out = format_protocol_detail(_Row(), chains_breakdown=None,
                                 stats=None, tz_offset=8)
    assert "📋 Aave" in out
    assert "状态: 启用 ✓" in out
