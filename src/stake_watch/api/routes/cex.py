from __future__ import annotations
import asyncio
import json
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from stake_watch.api.deps import get_config_store, get_storage
from stake_watch.collectors.cex.registry import build_cex_collector
from stake_watch.models.cex import CexVenue as CexVenueModel
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage

router = APIRouter()
logger = logging.getLogger(__name__)


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


@router.post("/refresh")
async def refresh_rates(storage: Storage = Depends(get_storage),
                        store: ConfigStore = Depends(get_config_store)):
    """Trigger an immediate CEX Earn rates refresh for all enabled venues.

    Mirrors what the scheduler's periodic job does, but on-demand from the UI.
    """
    venues = await store.list_enabled_cex_venues()
    pairs = []
    for v in venues:
        model = CexVenueModel(
            name=v.name, display_name=v.display_name, enabled=v.enabled,
            assets=json.loads(v.assets_json or "[]") or ["USDT", "USDC"],
            notes=v.notes,
        )
        collector = build_cex_collector(model)
        if collector is not None:
            pairs.append((model, collector))

    if not pairs:
        return {"success": True, "venues_refreshed": 0, "rates_written": 0,
                "errors": []}

    snaps = await asyncio.gather(*(c.collect() for _, c in pairs),
                                 return_exceptions=True)

    rates_written = 0
    errors: list[str] = []
    for (model, _), snap in zip(pairs, snaps):
        if isinstance(snap, BaseException):
            errors.append(f"{model.name}: {snap}")
            logger.warning("cex refresh %s crashed: %s", model.name, snap)
            continue
        if snap.rates:
            await storage.insert_cex_rates(snap.rates)
            rates_written += len(snap.rates)
        for err in snap.errors:
            errors.append(f"{snap.venue}: {err}")

    return {
        "success": True,
        "venues_refreshed": len(pairs),
        "rates_written": rates_written,
        "errors": errors,
    }