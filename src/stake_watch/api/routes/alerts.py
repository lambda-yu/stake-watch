from fastapi import APIRouter, Depends
from stake_watch.api.deps import get_storage
from stake_watch.storage.db import Storage

router = APIRouter()

@router.get("")
async def list_alerts(limit: int = 50, storage: Storage = Depends(get_storage)):
    alerts = await storage.get_recent_alerts(limit=limit)
    return [a.model_dump(mode="json") for a in alerts]
