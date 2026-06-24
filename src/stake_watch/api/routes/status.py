from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from stake_watch.api.deps import get_config_store, get_storage
from stake_watch.models.alert import Severity
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage
from stake_watch.storage.tables import (
    AlertRow,
    PositionRow,
    ProtocolStatsRow,
    TvlSnapshotRow,
)

router = APIRouter()


@router.get("")
async def system_status(storage: Storage = Depends(get_storage),
                         store: ConfigStore = Depends(get_config_store)):
    protos = await store.list_protocols()
    enabled = [p for p in protos if p.enabled]
    now = datetime.now(timezone.utc)

    async with storage._session_factory() as s:
        latest_collection = (await s.execute(
            select(func.max(ProtocolStatsRow.updated_at))
        )).scalar()
        latest_alert = (await s.execute(
            select(func.max(AlertRow.created_at))
        )).scalar()
        critical_24h = (await s.execute(
            select(func.count()).select_from(AlertRow)
            .where(AlertRow.severity == Severity.CRITICAL.value)
        )).scalar() or 0
        positions_count = (await s.execute(
            select(func.count()).select_from(PositionRow)
        )).scalar() or 0
        tvl_snapshot_count = (await s.execute(
            select(func.count()).select_from(TvlSnapshotRow)
        )).scalar() or 0

    def _age_seconds(ts):
        if not ts:
            return None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return int((now - ts).total_seconds())

    return {
        "status": "running",
        "version": "0.1.0",
        "now": now.isoformat(),
        "protocols": {
            "total": len(protos),
            "enabled": len(enabled),
        },
        "data": {
            "positions": positions_count,
            "tvl_snapshots": tvl_snapshot_count,
            "last_collection": latest_collection.isoformat() if latest_collection else None,
            "last_collection_age_seconds": _age_seconds(latest_collection),
        },
        "alerts": {
            "critical_total": critical_24h,
            "last_alert_at": latest_alert.isoformat() if latest_alert else None,
            "last_alert_age_seconds": _age_seconds(latest_alert),
        },
    }
