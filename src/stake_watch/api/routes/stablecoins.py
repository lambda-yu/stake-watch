from fastapi import APIRouter, Depends
from pydantic import BaseModel
from stake_watch.api.deps import get_storage, get_config_store
from stake_watch.storage.db import Storage
from stake_watch.storage.config_store import ConfigStore

router = APIRouter()


@router.get("")
async def get_stablecoin_snapshots(storage: Storage = Depends(get_storage)):
    snapshots = await storage.get_latest_stablecoin_snapshots()
    return [s.model_dump(mode="json") for s in snapshots]


@router.get("/dex-pools")
async def get_dex_pools():
    from stake_watch.collectors.stablecoin.dex_liquidity import DexLiquidityCollector
    collector = DexLiquidityCollector()
    pools = await collector.collect_pools()
    return [p.model_dump(mode="json") for p in pools]


@router.get("/reserves")
async def get_reserves(storage: Storage = Depends(get_storage), store: ConfigStore = Depends(get_config_store)):
    from stake_watch.collectors.stablecoin.reserves import evaluate_reserve_risk
    from decimal import Decimal

    snapshots = await storage.get_latest_stablecoin_snapshots()
    supply_map = {s.token: s.total_supply for s in snapshots}

    results = []
    for token in ["USDC", "USDT"]:
        report_date = await store.get_setting(f"reserves.{token.lower()}.report_date")
        total_reserves_raw = await store.get_setting(f"reserves.{token.lower()}.total_reserves")
        total_reserves = Decimal(str(total_reserves_raw)) if total_reserves_raw else None
        composition = await store.get_setting(f"reserves.{token.lower()}.composition") or {}
        circulating = supply_map.get(token, Decimal("0"))

        report = evaluate_reserve_risk(token, report_date, total_reserves, circulating, composition)
        results.append(report.model_dump(mode="json"))

    return results


@router.put("/reserves/{token}")
async def update_reserves(token: str, data: dict, store: ConfigStore = Depends(get_config_store)):
    token = token.upper()
    if "report_date" in data:
        await store.set_setting(f"reserves.{token.lower()}.report_date", data["report_date"])
    if "total_reserves" in data:
        await store.set_setting(f"reserves.{token.lower()}.total_reserves", data["total_reserves"])
    if "composition" in data:
        await store.set_setting(f"reserves.{token.lower()}.composition", data["composition"])
    return {"success": True}


@router.get("/report-config")
async def get_report_config(store: ConfigStore = Depends(get_config_store)):
    interval = await store.get_setting("stablecoin.report_interval") or 3600
    enabled = await store.get_setting("stablecoin.report_enabled")
    if enabled is None:
        enabled = True
    return {"interval": interval, "enabled": enabled}


class ReportConfigUpdate(BaseModel):
    interval: int | None = None
    enabled: bool | None = None


@router.put("/report-config")
async def update_report_config(data: ReportConfigUpdate, store: ConfigStore = Depends(get_config_store)):
    if data.interval is not None:
        await store.set_setting("stablecoin.report_interval", data.interval)
    if data.enabled is not None:
        await store.set_setting("stablecoin.report_enabled", data.enabled)
    interval = await store.get_setting("stablecoin.report_interval") or 3600
    enabled = await store.get_setting("stablecoin.report_enabled")
    if enabled is None:
        enabled = True
    return {"interval": interval, "enabled": enabled}


@router.post("/report/send")
async def send_report_now(storage: Storage = Depends(get_storage)):
    from stake_watch.alerts.stablecoin_report import send_stablecoin_report
    try:
        await send_stablecoin_report(storage)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/collect")
async def collect_now(storage: Storage = Depends(get_storage)):
    """Trigger immediate stablecoin data collection."""
    from stake_watch.collectors.stablecoin.price import StablecoinPriceCollector
    from stake_watch.collectors.stablecoin.supply import StablecoinSupplyCollector
    from stake_watch.risk.stablecoin_scorer import StablecoinScorer, ScoreInput
    from stake_watch.models.stablecoin import StablecoinRiskSnapshot
    from datetime import datetime, timezone
    from decimal import Decimal

    results = []
    try:
        price_collector = StablecoinPriceCollector()
        supply_collector = StablecoinSupplyCollector()
        prices = await price_collector.collect_prices()
        supplies = await supply_collector.collect_supply()

        scorer = StablecoinScorer()
        supply_map = {s.token: s for s in supplies}

        for p in prices:
            supply = supply_map.get(p.token)
            inp = ScoreInput(
                price=p.price, deviation=p.deviation,
                supply_change_24h_pct=supply.net_change_24h_pct if supply else 0,
                supply_change_7d_pct=supply.net_change_7d_pct if supply else 0,
            )
            score = scorer.score(inp)
            snap = StablecoinRiskSnapshot(
                token=p.token, price=p.price, deviation=p.deviation,
                total_supply=supply.total_circulating if supply else Decimal("0"),
                supply_change_24h_pct=supply.net_change_24h_pct if supply else 0,
                supply_change_7d_pct=supply.net_change_7d_pct if supply else 0,
                risk_level=score.level, risk_score=score.score,
                hard_trigger=score.hard_trigger, cex_spread_pct=0,
                updated_at=datetime.now(timezone.utc),
            )
            await storage.save_stablecoin_snapshot(snap)
            results.append({"token": p.token, "price": p.price, "risk_level": score.level})

        return {"success": True, "collected": results}
    except Exception as e:
        return {"success": False, "error": str(e)}
