"""Backup endpoints: download SQLite snapshot + JSON exports."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select

from stake_watch.api.deps import get_config_store, get_storage
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage
from stake_watch.storage.tables import (
    AlertRow,
    AppSettingsRow,
    PositionRow,
    ProtocolConfigRow,
    ProtocolStatsRow,
    RpcEndpointRow,
    TvlSnapshotRow,
    VaultSharePriceRow,
    WalletRow,
)

router = APIRouter()


def _sqlite_path_from_url(url: str) -> str | None:
    """Extract filesystem path from a sqlite+aiosqlite URL."""
    prefixes = ("sqlite+aiosqlite:///", "sqlite:///")
    for pre in prefixes:
        if url.startswith(pre):
            return url[len(pre):]
    return None


@router.get("/sqlite")
async def download_sqlite(storage: Storage = Depends(get_storage)):
    """Stream the raw SQLite file. Only works for sqlite DBs (not postgres etc)."""
    db_url = str(storage._engine.url)
    path = _sqlite_path_from_url(db_url)
    if not path:
        raise HTTPException(status_code=400,
                             detail="backup/sqlite only supports SQLite databases")
    try:
        with open(path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"DB file not found: {path}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition":
                  f'attachment; filename="stake_watch-{stamp}.sqlite"'},
    )


@router.get("/json")
async def export_json(storage: Storage = Depends(get_storage),
                       store: ConfigStore = Depends(get_config_store)):
    """Portable JSON dump of all config + recent operational data.

    Intended for migration / inspection / off-DB archiving. Heavy snapshot
    tables (tvl_snapshots, vault_share_prices) are capped at the last 1000 rows.
    """
    async with storage._session_factory() as s:
        protos = (await s.execute(select(ProtocolConfigRow))).scalars().all()
        wallets = (await s.execute(select(WalletRow))).scalars().all()
        rpcs = (await s.execute(select(RpcEndpointRow))).scalars().all()
        settings = (await s.execute(select(AppSettingsRow))).scalars().all()
        alerts = (await s.execute(
            select(AlertRow).order_by(AlertRow.created_at.desc()).limit(500)
        )).scalars().all()
        latest_stats = (await s.execute(
            select(ProtocolStatsRow).order_by(ProtocolStatsRow.updated_at.desc()).limit(50)
        )).scalars().all()
        tvl_snaps = (await s.execute(
            select(TvlSnapshotRow).order_by(TvlSnapshotRow.created_at.desc()).limit(1000)
        )).scalars().all()
        sp_snaps = (await s.execute(
            select(VaultSharePriceRow).order_by(VaultSharePriceRow.created_at.desc()).limit(1000)
        )).scalars().all()
        positions = (await s.execute(select(PositionRow))).scalars().all()

    def _row(obj, fields):
        out = {}
        for f in fields:
            v = getattr(obj, f, None)
            if isinstance(v, datetime):
                out[f] = v.isoformat()
            elif hasattr(v, "value"):
                out[f] = v.value
            else:
                out[f] = v
        return out

    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "version": "0.1.0",
        "protocols": [_row(p, ["id", "name", "chain", "collector", "enabled",
            "safety_rank", "safety_score", "reference_apy", "primary_risks",
            "vault_address", "defillama_slug", "pool_filter", "protocol_type",
            "risk_scores", "created_at", "updated_at"]) for p in protos],
        "wallets": [_row(w, ["id", "address", "label", "created_at"]) for w in wallets],
        "rpcs": [_row(r, ["chain", "primary_url", "fallback_urls"]) for r in rpcs],
        "settings": [_row(x, ["key", "value", "updated_at"]) for x in settings],
        "alerts": [_row(a, ["id", "rule_type", "severity", "protocol", "chain",
            "title", "message", "details_json", "dedup_key", "created_at"]) for a in alerts],
        "latest_protocol_stats": [_row(x, ["protocol", "chain", "tvl_usd",
            "pools_json", "updated_at"]) for x in latest_stats],
        "tvl_snapshots": [_row(x, ["protocol", "chain", "asset", "tvl_usd",
            "apy", "created_at"]) for x in tvl_snaps],
        "vault_share_prices": [_row(x, ["vault_address", "protocol",
            "share_price_usd", "created_at"]) for x in sp_snaps],
        "positions": [_row(x, ["wallet", "protocol", "chain", "asset",
            "position_type", "amount", "value_usd", "apy", "ltv",
            "health_factor", "vault_version", "updated_at"]) for x in positions],
    }
    body = json.dumps(payload, indent=2, default=str)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition":
                  f'attachment; filename="stake_watch-{stamp}.json"'},
    )
