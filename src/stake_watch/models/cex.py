from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel


class CexEarnRate(BaseModel):
    venue: str
    asset: str
    product_type: str = "flexible"
    apy_min: float
    apy_max: float
    tier_note: str | None = None
    raw_json: str | None = None
    updated_at: datetime


class VenueRateSnapshot(BaseModel):
    venue: str
    rates: list[CexEarnRate] = []
    errors: list[str] = []


class CexVenue(BaseModel):
    name: str
    display_name: str
    enabled: bool = True
    assets: list[str] = ["USDT", "USDC"]
    notes: str | None = None