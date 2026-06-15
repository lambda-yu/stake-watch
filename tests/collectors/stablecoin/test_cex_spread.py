from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from stake_watch.collectors.stablecoin.cex_spread import CexSpreadCollector

MOCK_TICKERS = {"tickers": [
    {"market": {"name": "Binance"}, "base": "USDC", "target": "USDT", "converted_last": {"usd": 1.0004}, "is_stale": False, "is_anomaly": False, "bid_ask_spread_percentage": 0.01},
    {"market": {"name": "Kraken"}, "base": "USDC", "target": "USD", "converted_last": {"usd": 0.9997}, "is_stale": False, "is_anomaly": False, "bid_ask_spread_percentage": 0.02},
    {"market": {"name": "Coinbase"}, "base": "USDC", "target": "EUR", "converted_last": {"usd": 0.9999}, "is_stale": False, "is_anomaly": False, "bid_ask_spread_percentage": 0.01},
    {"market": {"name": "Stale"}, "base": "USDC", "target": "USD", "converted_last": {"usd": 0.95}, "is_stale": True, "is_anomaly": False, "bid_ask_spread_percentage": 5.0},
]}

@pytest.mark.asyncio
async def test_collect_spread():
    collector = CexSpreadCollector()
    async def fake_get(*a, **k):
        r = MagicMock(); r.json = MagicMock(return_value=MOCK_TICKERS); r.raise_for_status = MagicMock(); return r
    with patch("httpx.AsyncClient.get", new=fake_get):
        spreads = await collector.collect_spreads()
    assert len(spreads) >= 1
    usdc = next(s for s in spreads if s.token == "USDC")
    assert usdc.max_price > usdc.min_price
    assert usdc.spread > 0
    assert usdc.num_exchanges >= 3  # Stale one filtered out

@pytest.mark.asyncio
async def test_spread_filters_stale():
    collector = CexSpreadCollector()
    async def fake_get(*a, **k):
        r = MagicMock(); r.json = MagicMock(return_value=MOCK_TICKERS); r.raise_for_status = MagicMock(); return r
    with patch("httpx.AsyncClient.get", new=fake_get):
        spreads = await collector.collect_spreads()
    usdc = next(s for s in spreads if s.token == "USDC")
    # Stale exchange at 0.95 should be filtered
    assert usdc.min_price > 0.99
