from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from stake_watch.collectors.aave.collector import AaveV3Collector
from stake_watch.models.common import Chain, PositionType

@pytest.mark.asyncio
async def test_collect_positions():
    c = AaveV3Collector(chain=Chain.BASE, protocol="aave_v3_base", pool_address="0xPool", rpc_url="https://fake")
    m = MagicMock()
    m.functions.getUserAccountData.return_value.call = AsyncMock(
        return_value=(10000 * 10**8, 5000 * 10**8, 3000 * 10**8, 8000, 7500, int(1.5 * 10**18)))
    with patch.object(c, '_get_pool_contract', return_value=m):
        pos = await c.collect_positions("0xW")
    assert len(pos) == 1
    assert pos[0].health_factor == 1.5
    assert pos[0].value_usd == Decimal("10000")

@pytest.mark.asyncio
async def test_collect_positions_zero():
    c = AaveV3Collector(chain=Chain.BASE, protocol="aave_v3_base", pool_address="0xP", rpc_url="https://f")
    m = MagicMock()
    m.functions.getUserAccountData.return_value.call = AsyncMock(return_value=(0,0,0,0,0,0))
    with patch.object(c, '_get_pool_contract', return_value=m):
        pos = await c.collect_positions("0xW")
    assert len(pos) == 0
