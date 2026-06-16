import json
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from stake_watch.api.deps import get_config_store, get_storage
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage

router = APIRouter()

class ProtocolCreate(BaseModel):
    name: str
    chain: str
    collector: str
    enabled: bool = True
    safety_rank: int | None = None
    safety_score: float | None = None
    reference_apy: str | None = None
    primary_risks: list[str] = []
    vault_address: str | None = None
    defillama_slug: str | None = None

def _to_dict(p):
    return {"id": p.id, "name": p.name, "chain": p.chain, "collector": p.collector,
        "enabled": p.enabled, "safety_rank": p.safety_rank, "safety_score": p.safety_score,
        "reference_apy": p.reference_apy, "primary_risks": json.loads(p.primary_risks) if p.primary_risks else [],
        "vault_address": p.vault_address, "defillama_slug": p.defillama_slug}


async def _enrich_with_stats(protocol_dict: dict, storage: Storage) -> dict:
    stats = await storage.get_latest_protocol_stats(protocol_dict["name"])
    if stats and stats.pools:
        tvl = float(stats.tvl_usd)
        usdc_pool = next((p for p in stats.pools if "USDC" in p.asset.upper() or "USD" in p.asset.upper()), stats.pools[0])
        protocol_dict["live_tvl_usd"] = tvl
        protocol_dict["live_apy"] = usdc_pool.supply_apy
        protocol_dict["live_pool_asset"] = usdc_pool.asset
        protocol_dict["stats_updated_at"] = stats.updated_at.isoformat()
    else:
        protocol_dict["live_tvl_usd"] = None
        protocol_dict["live_apy"] = None
    return protocol_dict


@router.get("")
async def list_protocols(store: ConfigStore = Depends(get_config_store),
                          storage: Storage = Depends(get_storage)):
    protos = await store.list_protocols()
    enriched = []
    for p in protos:
        d = _to_dict(p)
        d = await _enrich_with_stats(d, storage)
        enriched.append(d)
    return enriched

@router.post("", status_code=201)
async def add_protocol(data: ProtocolCreate, store: ConfigStore = Depends(get_config_store)):
    p = await store.add_protocol(**data.model_dump())
    return _to_dict(p)

@router.patch("/{protocol_id}/toggle")
async def toggle_protocol(protocol_id: int, store: ConfigStore = Depends(get_config_store)):
    await store.toggle_protocol(protocol_id)
    p = await store.get_protocol(protocol_id)
    return _to_dict(p)

@router.delete("/{protocol_id}", status_code=204)
async def delete_protocol(protocol_id: int, store: ConfigStore = Depends(get_config_store)):
    await store.delete_protocol(protocol_id)
    return Response(status_code=204)
