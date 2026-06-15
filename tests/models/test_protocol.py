from datetime import datetime, timezone
from decimal import Decimal
from stake_watch.models.common import Chain
from stake_watch.models.protocol import PoolStats, ProtocolStats

def test_protocol_stats():
    stats = ProtocolStats(chain=Chain.BASE, protocol="aave_v3_base", tvl_usd=Decimal("500000000"),
        pools=[PoolStats(pool_id="usdc-main", asset="USDC", supply_apy=3.17, borrow_apy=5.2,
            total_supply=Decimal("300000000"), total_borrow=Decimal("200000000"), utilization=0.667)],
        updated_at=datetime.now(timezone.utc))
    assert stats.tvl_usd == Decimal("500000000")
    assert len(stats.pools) == 1
    assert stats.pools[0].utilization == 0.667
