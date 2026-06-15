from unittest.mock import MagicMock, patch, AsyncMock
import pytest
from stake_watch.collectors.stablecoin.price import StablecoinPriceCollector

MOCK_CG = {"usd-coin": {"usd": 0.9998, "usd_24h_change": -0.01}, "tether": {"usd": 1.0001, "usd_24h_change": 0.005}}

@pytest.mark.asyncio
async def test_collect_prices():
    collector = StablecoinPriceCollector()
    cg_resp = MagicMock()
    cg_resp.json = MagicMock(return_value=MOCK_CG)
    cg_resp.raise_for_status = MagicMock()
    dl_resp = MagicMock()
    dl_resp.json = MagicMock(return_value={"peggedAssets": [
        {"symbol": "USDC", "name": "USD Coin", "price": 0.9999},
        {"symbol": "USDT", "name": "Tether", "price": 1.0002}]})
    dl_resp.raise_for_status = MagicMock()
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=[cg_resp, dl_resp]):
        prices = await collector.collect_prices()
    assert len(prices) == 2
    usdc = next(p for p in prices if p.token == "USDC")
    assert 0.999 < usdc.price < 1.001
    assert usdc.deviation < 0.01
