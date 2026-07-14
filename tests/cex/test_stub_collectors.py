"""Stub venues: fetch() must raise NotImplementedError; collect() must swallow it into errors."""
import pytest
from stake_watch.collectors.cex.binance import BinanceEarnCollector
from stake_watch.collectors.cex.bitget import BitgetEarnCollector


@pytest.mark.asyncio
async def test_binance_stub_swallows_into_errors():
    snap = await BinanceEarnCollector(["USDT", "USDC"]).collect()
    assert snap.rates == []
    assert len(snap.errors) == 1
    assert "unavailable" in snap.errors[0].lower()


@pytest.mark.asyncio
async def test_bitget_stub_swallows_into_errors():
    snap = await BitgetEarnCollector(["USDT", "USDC"]).collect()
    assert snap.rates == []
    assert len(snap.errors) == 1
    assert "unavailable" in snap.errors[0].lower()