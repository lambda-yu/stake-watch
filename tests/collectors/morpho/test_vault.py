from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest
from stake_watch.collectors.morpho.vault import read_vault_state

@pytest.mark.asyncio
async def test_read_vault_state():
    m = MagicMock()
    m.functions.totalAssets.return_value.call = AsyncMock(return_value=5_000_000_000_000)
    m.functions.totalSupply.return_value.call = AsyncMock(return_value=4_900_000_000_000)
    m.functions.convertToAssets.return_value.call = AsyncMock(return_value=1_020_408)
    m.functions.owner.return_value.call = AsyncMock(return_value="0xOwner")
    m.functions.curator.return_value.call = AsyncMock(return_value="0xCurator")
    m.functions.guardian.return_value.call = AsyncMock(return_value="0x" + "0" * 40)
    m.functions.fee.return_value.call = AsyncMock(return_value=0)
    m.functions.timelock.return_value.call = AsyncMock(return_value=86400)
    m.functions.supplyQueueLength.return_value.call = AsyncMock(return_value=3)
    m.functions.withdrawQueueLength.return_value.call = AsyncMock(return_value=3)
    state = await read_vault_state(m, "0xBEEF", decimals=6)
    assert state.total_assets == Decimal("5000000")
    assert state.owner == "0xOwner"
    assert state.timelock == 86400
    assert state.guardian is None
