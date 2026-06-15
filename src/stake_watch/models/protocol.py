from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel
from stake_watch.models.common import Chain

class PoolStats(BaseModel):
    pool_id: str
    asset: str
    supply_apy: float
    borrow_apy: float
    total_supply: Decimal
    total_borrow: Decimal
    utilization: float

class ProtocolStats(BaseModel):
    chain: Chain
    protocol: str
    tvl_usd: Decimal
    pools: list[PoolStats] = []
    updated_at: datetime
