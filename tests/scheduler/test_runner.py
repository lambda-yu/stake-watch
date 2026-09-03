from unittest.mock import AsyncMock, patch
import pytest
from stake_watch.collectors.base import CollectResult
from stake_watch.models.common import Chain
from stake_watch.scheduler.runner import CollectionRunner
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage

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


@pytest.fixture
async def real_storage():
    s = Storage("sqlite+aiosqlite:///:memory:")
    await s.initialize()
    store = ConfigStore(s._session_factory)
    await store.set_setting("telegram.bot_token", "test-token")
    await store.set_setting("telegram.chat_id", "12345")
    yield s
    await s.close()


@pytest.mark.asyncio
async def test_network_error_alert_saved_but_not_pushed_to_telegram(real_storage):
    bad = AsyncMock(); bad.chain = Chain.BASE; bad.protocol = "bad"
    bad.collect.return_value = CollectResult(
        positions=[], protocol_stats=None,
        errors=["bad: stats collection failed: "], is_network_error=True)
    runner = CollectionRunner(collectors=[bad], storage=real_storage, wallets=[""])
    runner.failure_alert_threshold = 1

    with patch("stake_watch.alerts.telegram.TelegramNotifier.send",
               new_callable=AsyncMock) as mock_send:
        await runner.run_collection_cycle()

    mock_send.assert_not_called()
    alerts = await real_storage.get_recent_alerts()
    assert len(alerts) == 1


@pytest.mark.asyncio
async def test_non_network_error_alert_pushed_to_telegram(real_storage):
    bad = AsyncMock(); bad.chain = Chain.BASE; bad.protocol = "bad"
    bad.collect.return_value = CollectResult(
        positions=[], protocol_stats=None,
        errors=["bad: stats collection failed: parse error"], is_network_error=False)
    runner = CollectionRunner(collectors=[bad], storage=real_storage, wallets=[""])
    runner.failure_alert_threshold = 1

    with patch("stake_watch.alerts.telegram.TelegramNotifier.send",
               new_callable=AsyncMock) as mock_send:
        await runner.run_collection_cycle()

    mock_send.assert_called_once()
