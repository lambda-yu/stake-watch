from datetime import datetime, timezone
from decimal import Decimal
import pytest
from stake_watch.models.common import Chain, PositionType
from stake_watch.models.position import Position
from stake_watch.models.protocol import PoolStats, ProtocolStats
from stake_watch.storage.db import Storage

@pytest.fixture
async def storage(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    s = Storage(db_url)
    await s.initialize()
    yield s
    await s.close()

@pytest.mark.asyncio
async def test_save_and_get_positions(storage):
    pos = Position(chain=Chain.BASE, protocol="aave_v3_base", wallet="0xTest", asset="USDC",
        position_type=PositionType.SUPPLY, amount=Decimal("10000"), value_usd=Decimal("10000"),
        apy=3.17, updated_at=datetime.now(timezone.utc))
    await storage.save_positions([pos])
    results = await storage.get_latest_positions(wallet="0xTest")
    assert len(results) == 1
    assert results[0].protocol == "aave_v3_base"
    assert results[0].amount == Decimal("10000")

@pytest.mark.asyncio
async def test_save_and_get_protocol_stats(storage):
    stats = ProtocolStats(chain=Chain.BASE, protocol="aave_v3_base", tvl_usd=Decimal("500000000"),
        pools=[PoolStats(pool_id="usdc", asset="USDC", supply_apy=3.17, borrow_apy=5.2,
            total_supply=Decimal("300000000"), total_borrow=Decimal("200000000"), utilization=0.667)],
        updated_at=datetime.now(timezone.utc))
    await storage.save_protocol_stats(stats)
    result = await storage.get_latest_protocol_stats("aave_v3_base")
    assert result is not None
    assert result.tvl_usd == Decimal("500000000")

@pytest.mark.asyncio
async def test_positions_upsert(storage):
    now = datetime.now(timezone.utc)
    pos1 = Position(chain=Chain.BASE, protocol="aave_v3_base", wallet="0xTest", asset="USDC",
        position_type=PositionType.SUPPLY, amount=Decimal("10000"), value_usd=Decimal("10000"), apy=3.0, updated_at=now)
    pos2 = Position(chain=Chain.BASE, protocol="aave_v3_base", wallet="0xTest", asset="USDC",
        position_type=PositionType.SUPPLY, amount=Decimal("15000"), value_usd=Decimal("15000"), apy=3.5, updated_at=now)
    await storage.save_positions([pos1])
    await storage.save_positions([pos2])
    results = await storage.get_latest_positions(wallet="0xTest")
    assert len(results) == 1
    assert results[0].amount == Decimal("15000")
