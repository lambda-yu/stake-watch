"""Tests for Jupiter Lend REST API stable-reserves fetcher."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stake_watch.collectors.jupiter.jupiter_api import fetch_jupiter_lend_stable_reserves


def _patch_get(json_data):
    client = MagicMock()
    resp = MagicMock()
    resp.json = MagicMock(return_value=json_data)
    resp.raise_for_status = MagicMock()
    client.get = AsyncMock(return_value=resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("httpx.AsyncClient", return_value=ctx)


def _token(symbol, *, decimals=6, price=1.0, total_assets=10_000_000_000,
           total_rate=500, supply=10_000_000_000, withdrawable=8_000_000_000):
    return {
        "asset": {"symbol": symbol, "decimals": decimals, "price": price},
        "totalAssets": total_assets,
        "totalRate": total_rate,
        "liquiditySupplyData": {"supply": supply, "withdrawable": withdrawable},
    }


@pytest.mark.asyncio
async def test_returns_usdc_and_usdt():
    with _patch_get([_token("USDC"), _token("USDT"), _token("SOL")]):
        out = await fetch_jupiter_lend_stable_reserves()
    assert [r["asset"] for r in out] == ["USDC", "USDT"]


@pytest.mark.asyncio
async def test_computes_apy_from_bps():
    with _patch_get([_token("USDC", total_rate=484)]):
        out = await fetch_jupiter_lend_stable_reserves()
    assert out[0]["apy"] == pytest.approx(4.84)


@pytest.mark.asyncio
async def test_computes_tvl_from_total_assets():
    # 10_000_000_000 raw / 10^6 decimals * $1 price = $10_000
    with _patch_get([_token("USDC", decimals=6, price=1.0,
                            total_assets=10_000_000_000)]):
        out = await fetch_jupiter_lend_stable_reserves()
    assert out[0]["tvl_usd"] == pytest.approx(10_000.0)


@pytest.mark.asyncio
async def test_computes_withdrawable_ratio():
    with _patch_get([_token("USDC", supply=10_000, withdrawable=7_000)]):
        out = await fetch_jupiter_lend_stable_reserves()
    assert out[0]["withdrawable_ratio"] == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_handles_missing_liquidity_data():
    token = _token("USDC")
    del token["liquiditySupplyData"]
    with _patch_get([token]):
        out = await fetch_jupiter_lend_stable_reserves()
    assert out[0]["withdrawable_ratio"] == 0


@pytest.mark.asyncio
async def test_returns_empty_for_no_stables():
    with _patch_get([_token("SOL"), _token("mSOL")]):
        out = await fetch_jupiter_lend_stable_reserves()
    assert out == []
