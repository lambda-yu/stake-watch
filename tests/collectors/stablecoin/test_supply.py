from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest
from stake_watch.collectors.stablecoin.supply import StablecoinSupplyCollector

MOCK_DL = {"peggedAssets": [
    {"symbol": "USDC", "name": "USD Coin",
     "circulating": {"peggedUSD": 75000000000},
     "circulatingPrevDay": {"peggedUSD": 74500000000},
     "circulatingPrevWeek": {"peggedUSD": 73000000000},
     "chainCirculating": {
         "Ethereum": {"current": {"peggedUSD": 48000000000}, "circulatingPrevDay": {"peggedUSD": 47500000000}},
         "Base": {"current": {"peggedUSD": 4200000000}, "circulatingPrevDay": {"peggedUSD": 4100000000}}}},
    {"symbol": "USDT", "name": "Tether",
     "circulating": {"peggedUSD": 186000000000},
     "circulatingPrevDay": {"peggedUSD": 185500000000},
     "circulatingPrevWeek": {"peggedUSD": 184000000000},
     "chainCirculating": {
         "Tron": {"current": {"peggedUSD": 87000000000}, "circulatingPrevDay": {"peggedUSD": 86800000000}},
         "Ethereum": {"current": {"peggedUSD": 80000000000}, "circulatingPrevDay": {"peggedUSD": 79500000000}}}}]}

@pytest.mark.asyncio
async def test_collect_supply():
    collector = StablecoinSupplyCollector()
    async def fake_get(*a, **k):
        r = MagicMock(); r.json = MagicMock(return_value=MOCK_DL); r.raise_for_status = MagicMock(); return r
    with patch("httpx.AsyncClient.get", new=fake_get):
        supplies = await collector.collect_supply()
    assert len(supplies) == 2
    usdc = next(s for s in supplies if s.token == "USDC")
    assert usdc.total_circulating == Decimal("75000000000")
    assert usdc.net_change_24h_pct > 0
    assert len(usdc.chain_breakdown) >= 2
