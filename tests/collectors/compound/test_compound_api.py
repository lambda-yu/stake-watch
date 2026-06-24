"""Tests for Compound V3 REST API stable-data fetcher."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from stake_watch.collectors.compound.compound_api import (
    COMETS,
    fetch_compound_v3_stable_data,
)


def _resp(json_data, status=200):
    r = MagicMock()
    r.json = MagicMock(return_value=json_data)
    if status >= 400:
        r.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("err", request=None, response=None))
    else:
        r.raise_for_status = MagicMock()
    return r


def _patch_get(responses_by_url: dict[str, dict]):
    """Mock httpx.AsyncClient.get to dispatch by URL substring."""
    async def fake_get(url, *args, **kwargs):
        for key, body in responses_by_url.items():
            if key in url:
                if body is None:
                    raise httpx.ConnectError("boom")
                return _resp(body)
        return _resp({})
    client = MagicMock()
    client.get = AsyncMock(side_effect=fake_get)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("httpx.AsyncClient", return_value=ctx)


def _summary(*, supply_apr=0.05, borrow_apr=0.07, base_usd_price=1.0,
              total_supply_value=1_000_000, total_borrow_value=500_000,
              total_collateral_value=700_000, utilization="500000000000000000"):
    return {
        "supply_apr": supply_apr, "borrow_apr": borrow_apr,
        "base_usd_price": base_usd_price,
        "total_supply_value": total_supply_value,
        "total_borrow_value": total_borrow_value,
        "total_collateral_value": total_collateral_value,
        "utilization": utilization,
    }


@pytest.mark.asyncio
async def test_parses_usdc_ethereum_comet():
    eth_usdc_addr = COMETS[0][1]  # mainnet USDC
    with _patch_get({eth_usdc_addr: _summary(total_supply_value=2_000_000,
                                              total_borrow_value=500_000)}):
        out = await fetch_compound_v3_stable_data()
    eth = [e for e in out if e["chain"] == "ETH"][0]
    usdc = eth["by_asset"]["USDC"]
    assert usdc["apy"] == pytest.approx(5.0)
    assert usdc["borrow_apy"] == pytest.approx(7.0)
    assert usdc["tvl_usd"] == pytest.approx(2_000_000)
    assert usdc["available_liquidity_usd"] == pytest.approx(1_500_000)
    assert usdc["withdrawable_ratio"] == pytest.approx(0.75)
    assert usdc["utilization"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_skips_failed_fetches():
    eth_usdc, eth_usdt, base_usdc = COMETS[0][1], COMETS[1][1], COMETS[2][1]
    with _patch_get({
        eth_usdc: _summary(),
        eth_usdt: None,  # raise -> _fetch_one returns None
        base_usdc: _summary(),
    }):
        out = await fetch_compound_v3_stable_data()
    chains = {e["chain"] for e in out}
    assert chains == {"ETH", "BASE"}
    # ETH only has USDC because USDT failed
    eth = [e for e in out if e["chain"] == "ETH"][0]
    assert list(eth["by_asset"]) == ["USDC"]


@pytest.mark.asyncio
async def test_computes_bad_debt_ratio_when_collateral_short():
    # Collateral 100k vs borrow 500k → coverage = 0.2 → bad_debt = 0.8
    eth_usdc = COMETS[0][1]
    with _patch_get({eth_usdc: _summary(total_borrow_value=500_000,
                                         total_collateral_value=100_000)}):
        out = await fetch_compound_v3_stable_data()
    usdc = out[0]["by_asset"]["USDC"]
    assert usdc["collateral_coverage"] == pytest.approx(0.2)
    assert usdc["bad_debt_ratio"] == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_handles_zero_supply_safely():
    eth_usdc = COMETS[0][1]
    with _patch_get({eth_usdc: _summary(total_supply_value=0)}):
        out = await fetch_compound_v3_stable_data()
    usdc = out[0]["by_asset"]["USDC"]
    assert usdc["tvl_usd"] == 0
    assert usdc["withdrawable_ratio"] == 0


@pytest.mark.asyncio
async def test_results_sorted_by_tvl_desc():
    eth_usdc, eth_usdt, base_usdc = COMETS[0][1], COMETS[1][1], COMETS[2][1]
    with _patch_get({
        eth_usdc: _summary(total_supply_value=1_000_000),
        eth_usdt: _summary(total_supply_value=500_000),
        base_usdc: _summary(total_supply_value=5_000_000),
    }):
        out = await fetch_compound_v3_stable_data()
    assert [e["chain"] for e in out] == ["BASE", "ETH"]
