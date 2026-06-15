from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from stake_watch.collectors.compound.collector import CompoundV3Collector
from stake_watch.models.common import Chain, PositionType

@pytest.mark.asyncio
async def test_collect_positions_supply():
    c = CompoundV3Collector(chain=Chain.BASE, protocol="compound_v3_usdc", comet_address="0xC", rpc_url="https://f")
    m = MagicMock()
    m.functions.balanceOf.return_value.call = AsyncMock(return_value=5000 * 10**6)
    m.functions.borrowBalanceOf.return_value.call = AsyncMock(return_value=0)
    with patch.object(c, '_get_comet_contract', return_value=m):
        pos = await c.collect_positions("0xW")
    assert len(pos) == 1
    assert pos[0].amount == Decimal("5000")
    assert pos[0].position_type == PositionType.SUPPLY

@pytest.mark.asyncio
async def test_collect_positions_zero():
    c = CompoundV3Collector(chain=Chain.BASE, protocol="compound_v3_usdc", comet_address="0xC", rpc_url="https://f")
    m = MagicMock()
    m.functions.balanceOf.return_value.call = AsyncMock(return_value=0)
    m.functions.borrowBalanceOf.return_value.call = AsyncMock(return_value=0)
    with patch.object(c, '_get_comet_contract', return_value=m):
        pos = await c.collect_positions("0xW")
    assert len(pos) == 0
