"""Tests for Kamino Lend REST API stable-reserves fetcher."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stake_watch.collectors.kamino.kamino_api import fetch_kamino_stable_reserves


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


def _reserve(token: str, supply_apy=0.05, total_supply_usd=1_000_000,
             total_borrow_usd=300_000):
    return {
        "liquidityToken": token,
        "supplyApy": supply_apy,
        "totalSupplyUsd": total_supply_usd,
        "totalBorrowUsd": total_borrow_usd,
    }


@pytest.mark.asyncio
async def test_returns_usdc_and_usdt_entries():
    with _patch_get([_reserve("USDC"), _reserve("usdt"), _reserve("SOL")]):
        out = await fetch_kamino_stable_reserves()
    assert [r["asset"] for r in out] == ["USDC", "USDT"]


@pytest.mark.asyncio
async def test_computes_apy_and_tvl():
    with _patch_get([_reserve("USDC", supply_apy=0.06, total_supply_usd=2_000_000)]):
        out = await fetch_kamino_stable_reserves()
    assert out[0]["apy"] == pytest.approx(6.0)
    assert out[0]["tvl_usd"] == pytest.approx(2_000_000)


@pytest.mark.asyncio
async def test_computes_utilization_and_withdrawable_ratio():
    with _patch_get([_reserve("USDC", total_supply_usd=1_000_000,
                              total_borrow_usd=800_000)]):
        out = await fetch_kamino_stable_reserves()
    assert out[0]["utilization"] == pytest.approx(0.8)
    assert out[0]["withdrawable_ratio"] == pytest.approx(0.2)
    assert out[0]["available_liquidity_usd"] == pytest.approx(200_000)


@pytest.mark.asyncio
async def test_returns_empty_when_no_stables():
    with _patch_get([_reserve("SOL"), _reserve("mSOL")]):
        out = await fetch_kamino_stable_reserves()
    assert out == []
