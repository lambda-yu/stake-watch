from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
import pytest
from stake_watch.collectors.morpho.governance import (
    GovernanceMonitor,
    GovernanceEvent,
    EVENT_TOPICS,
)


def _make_block_number_awaitable(value):
    """web3's AsyncEth.block_number is awaited directly (attribute access
    returns a coroutine). Build an awaitable that yields ``value`` so the
    expression ``await w3.eth.block_number`` resolves to ``value``."""

    async def _coro():
        return value

    return _coro()


def _make_block_number_raising(exc):
    async def _coro():
        raise exc

    return _coro()


@pytest.mark.asyncio
async def test_no_events():
    monitor = GovernanceMonitor(vault_address="0xVault", rpc_url="https://fake")
    mock_w3 = MagicMock()
    type(mock_w3.eth).block_number = PropertyMock(
        return_value=_make_block_number_awaitable(1000)
    )
    mock_w3.eth.get_logs = AsyncMock(return_value=[])
    mock_w3.to_checksum_address = lambda x: x
    with patch(
        "stake_watch.collectors.morpho.governance.AsyncWeb3", return_value=mock_w3
    ):
        events = await monitor.check_recent_events()
    assert events == []


@pytest.mark.asyncio
async def test_detects_event():
    monitor = GovernanceMonitor(vault_address="0xVault", rpc_url="https://fake")
    topic_bytes = bytes.fromhex(EVENT_TOPICS["SetCurator"][2:])
    mock_log = {
        "topics": [topic_bytes],
        "blockNumber": 999,
        "transactionHash": b"\x01" * 32,
        "data": b"\x02" * 32,
    }
    mock_w3 = MagicMock()
    type(mock_w3.eth).block_number = PropertyMock(
        return_value=_make_block_number_awaitable(1000)
    )
    mock_w3.eth.get_logs = AsyncMock(return_value=[mock_log])
    mock_w3.to_checksum_address = lambda x: x
    with patch(
        "stake_watch.collectors.morpho.governance.AsyncWeb3", return_value=mock_w3
    ):
        events = await monitor.check_recent_events()
    assert len(events) == 1
    assert events[0].event_type == "SetCurator"
    assert events[0].block_number == 999


@pytest.mark.asyncio
async def test_rpc_failure_returns_empty():
    monitor = GovernanceMonitor(vault_address="0xVault", rpc_url="https://fake")
    mock_w3 = MagicMock()
    type(mock_w3.eth).block_number = PropertyMock(
        return_value=_make_block_number_raising(Exception("timeout"))
    )
    with patch(
        "stake_watch.collectors.morpho.governance.AsyncWeb3", return_value=mock_w3
    ):
        events = await monitor.check_recent_events()
    assert events == []
