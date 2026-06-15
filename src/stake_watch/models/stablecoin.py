from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel

class SourcePrice(BaseModel):
    source: str
    price: float

class StablecoinPrice(BaseModel):
    token: str
    price: float
    deviation: float
    price_24h_change: float
    source: str
    sources: list[SourcePrice] = []
    updated_at: datetime

class ChainSupply(BaseModel):
    chain: str
    circulating: Decimal
    prev_day: Decimal
    change_24h_pct: float

class StablecoinSupply(BaseModel):
    token: str
    total_circulating: Decimal
    chain_breakdown: list[ChainSupply]
    net_change_24h: Decimal
    net_change_24h_pct: float
    net_change_7d_pct: float
    updated_at: datetime

class StablecoinRiskSnapshot(BaseModel):
    token: str
    price: float
    deviation: float
    total_supply: Decimal
    supply_change_24h_pct: float
    supply_change_7d_pct: float
    risk_level: str
    risk_score: float = 0.0
    hard_trigger: str | None = None
    cex_spread_pct: float = 0.0
    price_sources: list[SourcePrice] = []
    updated_at: datetime
