from unittest.mock import MagicMock, patch, AsyncMock
import pytest
from stake_watch.collectors.stablecoin.price import StablecoinPriceCollector


MOCK_CG = {"usd-coin": {"usd": 0.9998, "usd_24h_change": -0.01}, "tether": {"usd": 1.0001, "usd_24h_change": 0.005}}
MOCK_DL = {"peggedAssets": [
    {"symbol": "USDC", "name": "USD Coin", "price": 0.9999},
    {"symbol": "USDT", "name": "Tether", "price": 1.0002}]}
MOCK_KRAKEN = {"result": {"USDCUSD": {"c": ["0.9997"]}, "USDTZUSD": {"c": ["0.9993"]}}}


@pytest.mark.asyncio
async def test_collect_prices_multi_source():
    collector = StablecoinPriceCollector()
    with patch.object(collector, '_fetch_coingecko', return_value={
        "USDC": {"price": 0.9998, "change_24h": -0.01}, "USDT": {"price": 1.0001, "change_24h": 0.005}}), \
         patch.object(collector, '_fetch_defillama', return_value={
        "USDC": {"price": 0.9999}, "USDT": {"price": 1.0002}}), \
         patch.object(collector, '_fetch_binance', return_value={
        "USDC": {"price": 1.0004}}), \
         patch.object(collector, '_fetch_coinbase', return_value={
        "USDC": {"price": 1.0000}, "USDT": {"price": 0.9999}}), \
         patch.object(collector, '_fetch_kraken', return_value={
        "USDC": {"price": 0.9997}, "USDT": {"price": 0.9993}}), \
         patch.object(collector, '_fetch_okx', return_value={
        "USDC": {"price": 1.0004}}):
        prices = await collector.collect_prices()

    assert len(prices) == 2
    usdc = next(p for p in prices if p.token == "USDC")
    usdt = next(p for p in prices if p.token == "USDT")
    assert 0.999 < usdc.price < 1.001
    assert 0.999 < usdt.price < 1.001
    assert "6源" in usdc.source


@pytest.mark.asyncio
async def test_partial_failure():
    collector = StablecoinPriceCollector()
    with patch.object(collector, '_fetch_coingecko', return_value={
        "USDC": {"price": 0.9998}, "USDT": {"price": 1.0001}}), \
         patch.object(collector, '_fetch_defillama', side_effect=Exception("down")), \
         patch.object(collector, '_fetch_binance', side_effect=Exception("down")), \
         patch.object(collector, '_fetch_coinbase', side_effect=Exception("down")), \
         patch.object(collector, '_fetch_kraken', return_value={
        "USDC": {"price": 0.9997}, "USDT": {"price": 0.9993}}), \
         patch.object(collector, '_fetch_okx', side_effect=Exception("down")):
        prices = await collector.collect_prices()

    assert len(prices) == 2
    usdc = next(p for p in prices if p.token == "USDC")
    assert "2源" in usdc.source


@pytest.mark.asyncio
async def test_all_fail():
    collector = StablecoinPriceCollector()
    with patch.object(collector, '_fetch_coingecko', side_effect=Exception), \
         patch.object(collector, '_fetch_defillama', side_effect=Exception), \
         patch.object(collector, '_fetch_binance', side_effect=Exception), \
         patch.object(collector, '_fetch_coinbase', side_effect=Exception), \
         patch.object(collector, '_fetch_kraken', side_effect=Exception), \
         patch.object(collector, '_fetch_okx', side_effect=Exception):
        prices = await collector.collect_prices()
    assert prices == []
