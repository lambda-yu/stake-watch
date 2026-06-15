from fastapi import APIRouter, Depends
from stake_watch.api.deps import get_storage
from stake_watch.storage.db import Storage

router = APIRouter()

@router.get("")
async def get_stablecoin_snapshots(storage: Storage = Depends(get_storage)):
    snapshots = await storage.get_latest_stablecoin_snapshots()
    return [s.model_dump(mode="json") for s in snapshots]
