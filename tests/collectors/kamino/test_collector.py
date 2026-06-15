from decimal import Decimal
import pytest
from stake_watch.collectors.kamino.collector import KaminoCollector
from stake_watch.models.common import Chain

@pytest.mark.asyncio
async def test_collect_positions_empty():
    c = KaminoCollector(chain=Chain.SOLANA, protocol="kamino_usdc", rpc_url="https://f")
    assert await c.collect_positions("FakeWallet") == []

@pytest.mark.asyncio
async def test_collect_protocol_stats():
    c = KaminoCollector(chain=Chain.SOLANA, protocol="kamino_usdc", rpc_url="https://f")
    s = await c.collect_protocol_stats()
    assert s.protocol == "kamino_usdc"
    assert s.chain == Chain.SOLANA
