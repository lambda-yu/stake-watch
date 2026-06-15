import json
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from stake_watch.api.deps import get_config_store
from stake_watch.storage.config_store import ConfigStore

router = APIRouter()

class WalletCreate(BaseModel):
    chain: str
    address: str
    label: str | None = None

class WalletResponse(BaseModel):
    id: int
    chain: str
    address: str
    label: str | None

class IntervalsUpdate(BaseModel):
    positions: int | None = None
    protocol_stats: int | None = None
    stablecoin_price: int | None = None
    stablecoin_supply: int | None = None
    reserves: int | None = None

class RiskUpdate(BaseModel):
    liquidation_warning: float | None = None
    liquidation_critical: float | None = None
    depeg_warning: float | None = None
    depeg_critical: float | None = None
    tvl_crash_threshold: float | None = None
    apy_change_threshold: float | None = None

@router.get("/wallets")
async def list_wallets(store: ConfigStore = Depends(get_config_store)):
    wallets = await store.list_wallets()
    return [WalletResponse(id=w.id, chain=w.chain, address=w.address, label=w.label) for w in wallets]

@router.post("/wallets", status_code=201)
async def add_wallet(data: WalletCreate, store: ConfigStore = Depends(get_config_store)):
    w = await store.add_wallet(data.chain, data.address, data.label)
    return WalletResponse(id=w.id, chain=w.chain, address=w.address, label=w.label)

@router.delete("/wallets/{wallet_id}", status_code=204)
async def delete_wallet(wallet_id: int, store: ConfigStore = Depends(get_config_store)):
    await store.delete_wallet(wallet_id)
    return Response(status_code=204)

@router.get("/intervals")
async def get_intervals(store: ConfigStore = Depends(get_config_store)):
    settings = await store.load_app_settings()
    return settings.intervals.model_dump()

@router.put("/intervals")
async def update_intervals(data: IntervalsUpdate, store: ConfigStore = Depends(get_config_store)):
    for field, value in data.model_dump(exclude_none=True).items():
        await store.set_setting(f"intervals.{field}", value)
    settings = await store.load_app_settings()
    return settings.intervals.model_dump()

@router.get("/risk")
async def get_risk(store: ConfigStore = Depends(get_config_store)):
    settings = await store.load_app_settings()
    return settings.risk.model_dump()

@router.put("/risk")
async def update_risk(data: RiskUpdate, store: ConfigStore = Depends(get_config_store)):
    for field, value in data.model_dump(exclude_none=True).items():
        await store.set_setting(f"risk.{field}", value)
    settings = await store.load_app_settings()
    return settings.risk.model_dump()
