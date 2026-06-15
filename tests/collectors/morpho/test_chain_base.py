from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from stake_watch.collectors.morpho.chain_base import check_base_network

@pytest.mark.asyncio
async def test_healthy():
    m = MagicMock()
    m.eth.get_block = AsyncMock(return_value={"number": 1000000, "timestamp": 1718400000, "baseFeePerGas": 100000000})
    with patch("stake_watch.collectors.morpho.chain_base.time") as mt:
        mt.time.return_value = 1718400005
        s = await check_base_network(m)
    assert s.is_healthy is True
    assert s.block_age_seconds == 5.0

@pytest.mark.asyncio
async def test_stale():
    m = MagicMock()
    m.eth.get_block = AsyncMock(return_value={"number": 1000000, "timestamp": 1718400000, "baseFeePerGas": 100000000})
    with patch("stake_watch.collectors.morpho.chain_base.time") as mt:
        mt.time.return_value = 1718400120
        s = await check_base_network(m)
    assert s.is_healthy is False
