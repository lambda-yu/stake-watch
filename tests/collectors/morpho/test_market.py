from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest
from stake_watch.collectors.morpho.market import read_market_allocations

@pytest.mark.asyncio
async def test_read_market_allocations():
    mv = MagicMock()
    mv.functions.withdrawQueueLength.return_value.call = AsyncMock(return_value=1)
    mv.functions.withdrawQueue.return_value.call = AsyncMock(return_value=b'\x01' * 32)
    mv.functions.config.return_value.call = AsyncMock(return_value=(2_000_000_000_000, True, 0))

    mm = MagicMock()
    mm.functions.idToMarketParams.return_value.call = AsyncMock(
        return_value=("0xUSDC", "0xWETH", "0xOracle", "0xIRM", 860000000000000000))
    mm.functions.market.return_value.call = AsyncMock(
        return_value=(1_000_000_000_000, 900_000_000_000, 800_000_000_000, 700_000_000_000, 0, 0))
    mm.functions.position.return_value.call = AsyncMock(return_value=(500_000_000_000, 0, 0))

    allocs = await read_market_allocations(mv, mm, "0xVault", decimals=6, total_vault_assets=Decimal("1000000"))
    assert len(allocs) == 1
    assert allocs[0].lltv == 0.86
    assert allocs[0].utilization == 0.8
