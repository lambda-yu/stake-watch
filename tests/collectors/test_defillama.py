from unittest.mock import MagicMock, patch
import pytest
from stake_watch.collectors.defillama import DefiLlamaCollector
from stake_watch.models.common import Chain

@pytest.fixture
def collector():
    return DefiLlamaCollector(chain=Chain.BASE, protocol="aave_v3_base",
        defillama_slug="aave-v3", chain_filter="Base")

MOCK_POOLS_RESPONSE = {
    "data": [
        {"pool": "pool-id-1", "chain": "Base", "project": "aave-v3", "symbol": "USDC", "tvlUsd": 300000000, "apy": 3.17},
        {"pool": "pool-id-2", "chain": "Base", "project": "aave-v3", "symbol": "WETH", "tvlUsd": 200000000, "apy": 1.5},
        {"pool": "pool-id-3", "chain": "Ethereum", "project": "aave-v3", "symbol": "USDC", "tvlUsd": 500000000, "apy": 4.0},
    ]
}

@pytest.mark.asyncio
async def test_collect_protocol_stats(collector):
    async def fake_get(*args, **kwargs):
        resp = MagicMock()
        resp.json = MagicMock(return_value=MOCK_POOLS_RESPONSE)
        resp.raise_for_status = MagicMock(return_value=None)
        return resp
    with patch("httpx.AsyncClient.get", new=fake_get):
        stats = await collector.collect_protocol_stats()
    assert stats.protocol == "aave_v3_base"
    assert stats.chain == Chain.BASE
    assert len(stats.pools) >= 1
    usdc_pool = next(p for p in stats.pools if p.asset == "USDC")
    assert usdc_pool.supply_apy == 3.17

@pytest.mark.asyncio
async def test_chain_filter_applied(collector):
    async def fake_get(*args, **kwargs):
        resp = MagicMock()
        resp.json = MagicMock(return_value=MOCK_POOLS_RESPONSE)
        resp.raise_for_status = MagicMock(return_value=None)
        return resp
    with patch("httpx.AsyncClient.get", new=fake_get):
        stats = await collector.collect_protocol_stats()
    assert stats.chain == Chain.BASE
    assert len(stats.pools) == 2  # Ethereum pool filtered out
