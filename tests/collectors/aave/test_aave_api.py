"""Tests for Aave V3 GraphQL stable-data fetcher."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from stake_watch.collectors.aave.aave_api import fetch_aave_v3_stable_data


def _resp(json_data, status=200):
    r = MagicMock()
    r.json = MagicMock(return_value=json_data)
    r.raise_for_status = MagicMock(side_effect=None) if status < 400 else MagicMock(
        side_effect=httpx.HTTPStatusError("err", request=None, response=None))
    return r


def _patch_post(json_data):
    client = MagicMock()
    client.post = AsyncMock(return_value=_resp(json_data))
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("httpx.AsyncClient", return_value=ctx)


def _reserve(symbol: str, *, supply_apy=0.05, supply_total=1_000_000, supply_cap_amt=2_000_000,
             borrow_apy=0.08, util=0.5, avail_usd=500_000, borrow_total=500_000,
             borrow_cap_amt=1_000_000, size_usd=1_000_000):
    return {
        "underlyingToken": {"symbol": symbol},
        "size": {"usd": size_usd},
        "supplyInfo": {
            "apy": {"value": supply_apy},
            "supplyCap": {"amount": {"value": supply_cap_amt}, "usd": supply_cap_amt},
            "total": {"value": supply_total},
            "supplyCapReached": False,
        },
        "borrowInfo": {
            "apy": {"value": borrow_apy},
            "utilizationRate": {"value": util},
            "availableLiquidity": {"amount": {"value": avail_usd}, "usd": avail_usd},
            "borrowCap": {"amount": {"value": borrow_cap_amt}, "usd": borrow_cap_amt},
            "total": {"amount": {"value": borrow_total}, "usd": borrow_total},
            "borrowCapReached": False,
        },
    }


@pytest.mark.asyncio
async def test_parses_known_chain_and_assets():
    payload = {"data": {"markets": [{
        "name": "AaveV3Ethereum",
        "chain": {"chainId": 1, "name": "Ethereum"},
        "reserves": [_reserve("USDC", size_usd=1_000_000),
                     _reserve("USDT", size_usd=500_000)],
    }]}}
    with _patch_post(payload):
        out = await fetch_aave_v3_stable_data()
    assert len(out) == 1
    eth = out[0]
    assert eth["chain"] == "ETH"
    assert "USDC" in eth["by_asset"]
    assert "USDT" in eth["by_asset"]
    assert eth["pools"] == 2
    assert eth["tvl_usd"] == 1_500_000
    # apy is mean of two assets (both 5%)
    assert eth["apy"] == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_skips_sub_markets():
    payload = {"data": {"markets": [
        {"name": "AaveV3EthereumLido",
         "chain": {"chainId": 1, "name": "Ethereum"},
         "reserves": [_reserve("USDC")]},
        {"name": "AaveV3EthereumEtherFi",
         "chain": {"chainId": 1, "name": "Ethereum"},
         "reserves": [_reserve("USDC")]},
    ]}}
    with _patch_post(payload):
        out = await fetch_aave_v3_stable_data()
    assert out == []


@pytest.mark.asyncio
async def test_skips_unknown_chain_id():
    payload = {"data": {"markets": [{
        "name": "AaveV3Polygon",
        "chain": {"chainId": 137, "name": "Polygon"},
        "reserves": [_reserve("USDC")],
    }]}}
    with _patch_post(payload):
        out = await fetch_aave_v3_stable_data()
    assert out == []


@pytest.mark.asyncio
async def test_skips_non_stablecoins():
    payload = {"data": {"markets": [{
        "name": "AaveV3Base",
        "chain": {"chainId": 8453, "name": "Base"},
        "reserves": [_reserve("WETH"), _reserve("cbBTC")],
    }]}}
    with _patch_post(payload):
        out = await fetch_aave_v3_stable_data()
    assert out == []


@pytest.mark.asyncio
async def test_computes_cap_usage_and_withdrawable_ratio():
    payload = {"data": {"markets": [{
        "name": "AaveV3Base",
        "chain": {"chainId": 8453, "name": "Base"},
        "reserves": [_reserve("USDC", supply_total=1_600_000, supply_cap_amt=2_000_000,
                              borrow_total=400_000, borrow_cap_amt=1_000_000,
                              avail_usd=200_000, size_usd=1_000_000)],
    }]}}
    with _patch_post(payload):
        out = await fetch_aave_v3_stable_data()
    usdc = out[0]["by_asset"]["USDC"]
    assert usdc["supply_cap_usage"] == pytest.approx(0.8)
    assert usdc["borrow_cap_usage"] == pytest.approx(0.4)
    assert usdc["withdrawable_ratio"] == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_results_sorted_by_tvl_desc():
    payload = {"data": {"markets": [
        {"name": "AaveV3Base", "chain": {"chainId": 8453, "name": "Base"},
         "reserves": [_reserve("USDC", size_usd=500_000)]},
        {"name": "AaveV3Ethereum", "chain": {"chainId": 1, "name": "Ethereum"},
         "reserves": [_reserve("USDC", size_usd=2_000_000)]},
    ]}}
    with _patch_post(payload):
        out = await fetch_aave_v3_stable_data()
    assert [e["chain"] for e in out] == ["ETH", "BASE"]


@pytest.mark.asyncio
async def test_empty_markets_returns_empty():
    with _patch_post({"data": {"markets": []}}):
        out = await fetch_aave_v3_stable_data()
    assert out == []


@pytest.mark.asyncio
async def test_handles_null_data_field():
    with _patch_post({"data": None}):
        out = await fetch_aave_v3_stable_data()
    assert out == []
