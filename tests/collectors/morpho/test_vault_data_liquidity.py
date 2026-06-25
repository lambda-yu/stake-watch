"""Tests for Morpho GraphQL fetch_vault_data utilization / withdrawable_ratio."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from stake_watch.collectors.morpho.morpho_api import fetch_vault_data


def _patch_post(payload):
    client = MagicMock()
    resp = MagicMock()
    resp.json = MagicMock(return_value=payload)
    resp.raise_for_status = MagicMock()
    client.post = AsyncMock(return_value=resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("httpx.AsyncClient", return_value=ctx)


def _vault_payload(total_assets, allocations):
    return {"data": {"vaults": {"items": [{
        "name": "Test Vault", "address": "0xV", "symbol": "TV",
        "asset": {"symbol": "USDC"},
        "state": {
            "totalAssetsUsd": total_assets,
            "netApy": 0.045, "apy": 0.05,
            "sharePriceUsd": 1.0001,
            "allocation": [
                {"supplyAssetsUsd": s, "market": {"state": {"liquidityAssetsUsd": l}}}
                for s, l in allocations
            ],
        },
    }]}}}


@pytest.mark.asyncio
async def test_basic_fields_preserved():
    with _patch_post(_vault_payload(1_000_000, [(900_000, 500_000)])):
        out = await fetch_vault_data("0xV", "base")
    assert out["tvl_usd"] == 1_000_000
    assert out["apy"] == pytest.approx(5.0)
    assert out["share_price_usd"] == 1.0001
    assert out["asset"] == "USDC"


@pytest.mark.asyncio
async def test_withdrawable_when_market_has_excess_liquidity():
    # 1M total = 900K supplied (market has 1.5M free) + 100K idle
    # withdrawable = min(900K, 1.5M) + 100K = 1M
    with _patch_post(_vault_payload(1_000_000, [(900_000, 1_500_000)])):
        out = await fetch_vault_data("0xV", "base")
    assert out["withdrawable_usd"] == 1_000_000
    assert out["withdrawable_ratio"] == pytest.approx(1.0)
    assert out["utilization"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_withdrawable_when_market_constrained():
    # 1M total = 900K supplied (only 200K free in market) + 100K idle
    # withdrawable = min(900K, 200K) + 100K = 300K → ratio 0.30, util 0.70
    with _patch_post(_vault_payload(1_000_000, [(900_000, 200_000)])):
        out = await fetch_vault_data("0xV", "base")
    assert out["withdrawable_usd"] == pytest.approx(300_000)
    assert out["withdrawable_ratio"] == pytest.approx(0.30)
    assert out["utilization"] == pytest.approx(0.70)


@pytest.mark.asyncio
async def test_withdrawable_multi_market():
    # 1M total = 400K (market 200K free) + 300K (market 1M free) + 300K idle
    # withdrawable = min(400,200) + min(300,1000) + 300 = 200+300+300 = 800 → ratio 0.8
    with _patch_post(_vault_payload(1_000_000,
                                      [(400_000, 200_000), (300_000, 1_000_000)])):
        out = await fetch_vault_data("0xV", "base")
    assert out["withdrawable_usd"] == pytest.approx(800_000)
    assert out["withdrawable_ratio"] == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_withdrawable_with_zero_allocations_means_all_idle():
    # No supplies — everything sits idle, withdrawable = total_assets
    with _patch_post(_vault_payload(1_000_000, [])):
        out = await fetch_vault_data("0xV", "base")
    assert out["withdrawable_ratio"] == pytest.approx(1.0)
    assert out["utilization"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_zero_tvl_returns_zero_ratios_safely():
    with _patch_post(_vault_payload(0, [])):
        out = await fetch_vault_data("0xV", "base")
    assert out["withdrawable_ratio"] == 0.0
    assert out["utilization"] == 0.0
