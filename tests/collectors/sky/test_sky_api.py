"""Tests for Sky sUSDS on-chain reader (SSR + TVL)."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stake_watch.collectors.sky.sky_api import RAY, fetch_sky_susds_data


def _build_w3_mock(ssr_raw: int, total_shares: int, total_assets: int):
    """Mock AsyncWeb3 with a contract whose function calls return the given values."""
    w3 = MagicMock()
    w3.to_checksum_address = MagicMock(side_effect=lambda a: a)
    contract = MagicMock()
    contract.functions.ssr.return_value.call = AsyncMock(return_value=ssr_raw)
    contract.functions.totalSupply.return_value.call = AsyncMock(return_value=total_shares)
    contract.functions.convertToAssets.return_value.call = AsyncMock(return_value=total_assets)
    w3.eth.contract = MagicMock(return_value=contract)
    return w3


@pytest.mark.asyncio
async def test_returns_apy_and_tvl_with_curated_rate():
    # SSR for ~5% APY ≈ 1 + 0.05/seconds_per_year per second (in RAY units)
    # Use a sample value that maps cleanly.
    SECONDS = 365 * 86400
    per_second = (Decimal("1.05") ** (Decimal(1) / Decimal(SECONDS)))
    ssr_raw = int(per_second * RAY)
    # 100M USDS in 18 decimals
    total_assets_raw = 100_000_000 * 10**18

    with patch("stake_watch.collectors.sky.sky_api.AsyncWeb3",
                return_value=_build_w3_mock(ssr_raw, 10**18, total_assets_raw)):
        out = await fetch_sky_susds_data("https://rpc")

    assert out is not None
    assert out["asset"] == "USDS"
    assert out["apy"] == pytest.approx(5.0, abs=0.01)
    assert out["tvl_usd"] == pytest.approx(100_000_000)


@pytest.mark.asyncio
async def test_returns_none_when_ssr_is_zero():
    with patch("stake_watch.collectors.sky.sky_api.AsyncWeb3",
                return_value=_build_w3_mock(0, 0, 0)):
        out = await fetch_sky_susds_data("https://rpc")
    assert out is None


@pytest.mark.asyncio
async def test_returns_none_on_rpc_exception():
    w3 = MagicMock()
    w3.to_checksum_address = MagicMock(side_effect=lambda a: a)
    contract = MagicMock()
    contract.functions.ssr.return_value.call = AsyncMock(side_effect=Exception("rpc down"))
    w3.eth.contract = MagicMock(return_value=contract)
    with patch("stake_watch.collectors.sky.sky_api.AsyncWeb3", return_value=w3):
        out = await fetch_sky_susds_data("https://rpc")
    assert out is None
