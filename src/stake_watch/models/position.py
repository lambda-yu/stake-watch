from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel
from stake_watch.models.common import Chain, PositionType

class Position(BaseModel):
    chain: Chain
    protocol: str
    wallet: str
    asset: str
    position_type: PositionType
    amount: Decimal
    value_usd: Decimal
    apy: float
    ltv: float | None = None
    health_factor: float | None = None
    vault_version: str | None = None
    updated_at: datetime
