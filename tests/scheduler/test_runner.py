from unittest.mock import AsyncMock
import pytest
from stake_watch.collectors.base import CollectResult
from stake_watch.models.common import Chain
from stake_watch.scheduler.runner import CollectionRunner

@pytest.fixture
def mock_collector():
    c = AsyncMock()
    c.chain = Chain.BASE
    c.protocol = "test_protocol"
    c.collect.return_value = CollectResult(positions=[], protocol_stats=None, errors=[])
    return c

@pytest.fixture
def mock_storage():
    return AsyncMock()

@pytest.mark.asyncio
async def test_run_collection_cycle(mock_collector, mock_storage):
    runner = CollectionRunner(collectors=[mock_collector], storage=mock_storage, wallets=["0xTest"])
    results = await runner.run_collection_cycle()
    assert len(results) == 1
    mock_collector.collect.assert_called_once_with("0xTest")

@pytest.mark.asyncio
async def test_collector_failure_isolated(mock_storage):
    good = AsyncMock(); good.chain = Chain.BASE; good.protocol = "good"
    good.collect.return_value = CollectResult(positions=[], protocol_stats=None, errors=[])
    bad = AsyncMock(); bad.chain = Chain.BASE; bad.protocol = "bad"
    bad.collect.side_effect = Exception("RPC timeout")
    runner = CollectionRunner(collectors=[good, bad], storage=mock_storage, wallets=["0xTest"])
    results = await runner.run_collection_cycle()
    good.collect.assert_called_once()
    assert len(results) == 2
    assert any(r.errors for r in results)
