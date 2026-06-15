import json
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from stake_watch.api.deps import get_config_store
from stake_watch.storage.config_store import ConfigStore

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

@router.get("")
async def list_protocols(store: ConfigStore = Depends(get_config_store)):
    protos = await store.list_protocols()
    return [_to_dict(p) for p in protos]

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
