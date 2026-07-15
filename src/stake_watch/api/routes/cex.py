from __future__ import annotations
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from stake_watch.api.deps import get_config_store, get_storage
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage

router = APIRouter()


class VenueOut(BaseModel):
    name: str
    display_name: str
    enabled: bool
    assets: list[str]
    notes: str | None = None


class VenuePatch(BaseModel):
    enabled: bool | None = None
    assets: list[str] | None = None
    notes: str | None = None


class RateOut(BaseModel):
    venue: str
    venue_display: str
    asset: str
    product_type: str
    apy_min: float
    apy_max: float
    tier_note: str | None = None
    updated_at: datetime


def _venue_out(row) -> VenueOut:
    return VenueOut(
        name=row.name, display_name=row.display_name, enabled=row.enabled,
        assets=json.loads(row.assets_json or "[]") or ["USDT", "USDC"],
        notes=row.notes,
    )


@router.get("/venues", response_model=list[VenueOut])
async def list_venues(store: ConfigStore = Depends(get_config_store)):
    return [_venue_out(r) for r in await store.list_cex_venues()]


@router.patch("/venues/{name}", response_model=VenueOut)
async def patch_venue(name: str, body: VenuePatch,
                      store: ConfigStore = Depends(get_config_store)):
    row = await store.patch_cex_venue(name, enabled=body.enabled,
                                      assets=body.assets, notes=body.notes)
    if not row:
        raise HTTPException(404, f"venue '{name}' not found")
    return _venue_out(row)


@router.get("/rates/latest", response_model=list[RateOut])
async def latest_rates(storage: Storage = Depends(get_storage),
                       store: ConfigStore = Depends(get_config_store)):
    venues = {v.name: v.display_name for v in await store.list_cex_venues()}
    rows = await storage.list_latest_cex_rates()
    out = [RateOut(
        venue=r.venue, venue_display=venues.get(r.venue, r.venue),
        asset=r.asset, product_type=r.product_type,
        apy_min=r.apy_min, apy_max=r.apy_max,
        tier_note=r.tier_note, updated_at=r.updated_at,
    ) for r in rows]
    return sorted(out, key=lambda x: x.apy_max, reverse=True)


@router.get("/rates/history", response_model=list[RateOut])
async def history_rates(venue: str, asset: str, since: datetime | None = None,
                        limit: int = 100,
                        storage: Storage = Depends(get_storage),
                        store: ConfigStore = Depends(get_config_store)):
    venues = {v.name: v.display_name for v in await store.list_cex_venues()}
    rows = await storage.list_cex_history(venue=venue, asset=asset,
                                          since=since, limit=limit)
    return [RateOut(
        venue=r.venue, venue_display=venues.get(r.venue, r.venue),
        asset=r.asset, product_type=r.product_type,
        apy_min=r.apy_min, apy_max=r.apy_max,
        tier_note=r.tier_note, updated_at=r.updated_at,
    ) for r in rows]