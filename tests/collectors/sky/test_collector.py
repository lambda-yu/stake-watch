from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from stake_watch.collectors.sky.collector import SkySusdsCollector
from stake_watch.models.common import Chain, PositionType

@pytest.mark.asyncio
async def test_collect_positions():
    c = SkySusdsCollector(chain=Chain.ETHEREUM, protocol="sky_susds", susds_address="0xS", rpc_url="https://f")
    m = MagicMock()
    m.functions.balanceOf.return_value.call = AsyncMock(return_value=5000 * 10**18)
    m.functions.convertToAssets.return_value.call = AsyncMock(return_value=5100 * 10**18)
    with patch.object(c, '_get_contract', return_value=m):
        pos = await c.collect_positions("0xW")
    assert len(pos) == 1
    assert pos[0].amount == Decimal("5100")
    assert pos[0].position_type == PositionType.VAULT

@pytest.mark.asyncio
async def test_collect_positions_zero():
    c = SkySusdsCollector(chain=Chain.ETHEREUM, protocol="sky_susds", susds_address="0xS", rpc_url="https://f")
    m = MagicMock()
    m.functions.balanceOf.return_value.call = AsyncMock(return_value=0)
    with patch.object(c, '_get_contract', return_value=m):
        pos = await c.collect_positions("0xW")
    assert len(pos) == 0
