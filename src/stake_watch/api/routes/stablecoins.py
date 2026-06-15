from datetime import datetime, timezone
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
    for token in ["USDC", "USDT", "USD0", "USD1"]:
        report_date = await store.get_setting(f"reserves.{token.lower()}.report_date")
        last_fetched = await store.get_setting(f"reserves.{token.lower()}.last_fetched")
        total_reserves_raw = await store.get_setting(f"reserves.{token.lower()}.total_reserves")
        total_reserves = Decimal(str(total_reserves_raw)) if total_reserves_raw else None

        live_supply_raw = await store.get_setting(f"reserves.{token.lower()}.total_supply_live")
        circulating = supply_map.get(token, Decimal("0"))
        if circulating == 0 and live_supply_raw:
            circulating = Decimal(str(live_supply_raw))
        if circulating == 0 and total_reserves:
            circulating = total_reserves

        composition = await store.get_setting(f"reserves.{token.lower()}.composition") or {}

        report = evaluate_reserve_risk(token, report_date, total_reserves, circulating, composition)
        report_dict = report.model_dump(mode="json")
        report_dict["last_fetched"] = last_fetched
        results.append(report_dict)

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


@router.post("/reserves/fetch")
async def fetch_reserves_live(store: ConfigStore = Depends(get_config_store)):
    """Auto-fetch reserve data from Circle API and Tether API."""
    from stake_watch.collectors.stablecoin.reserves_fetcher import fetch_tether_reserves, fetch_circle_supply
    results = {}

    tether = await fetch_tether_reserves()
    if tether:
        assets = float(tether["total_assets"])
        liabilities = float(tether["total_liabilities"])
        equity = float(tether["equity"])
        await store.set_setting("reserves.usdt.total_reserves", assets)
        await store.set_setting("reserves.usdt.total_liabilities", liabilities)
        await store.set_setting("reserves.usdt.equity", equity)
        await store.set_setting("reserves.usdt.coverage_ratio", tether["coverage_ratio"])
        await store.set_setting("reserves.usdt.last_fetched",
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))
        await store.set_setting("reserves.usdt.composition", {
            "总资产": round(assets / 1e9, 1),
            "总负债": round(liabilities / 1e9, 1),
            "股东权益": round(equity / 1e9, 1),
            "_来源": "Tether API (实时数据)",
        })
        top_chains = sorted(tether.get("chains", {}).items(), key=lambda x: x[1], reverse=True)[:5]
        results["USDT"] = {
            "total_assets": assets,
            "total_liabilities": liabilities,
            "coverage_ratio": tether["coverage_ratio"],
            "chains": len(tether.get("chains", {})),
            "top_chains": {k: round(v / 1e9, 2) for k, v in top_chains},
        }

    circle = await fetch_circle_supply()
    if circle:
        supply = float(circle["total_supply"])
        await store.set_setting("reserves.usdc.total_supply_live", supply)
        await store.set_setting("reserves.usdc.total_reserves", supply)
        await store.set_setting("reserves.usdc.last_fetched",
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))
        top_chains = sorted(circle.get("chains", {}).items(), key=lambda x: x[1], reverse=True)[:5]
        await store.set_setting("reserves.usdc.composition", {
            "BlackRock USDXX (国债+回购)": 80,
            "银行存款": 20,
            "_来源": "Circle API (供应量=储备，Deloitte 每月审计)",
        })
        results["USDC"] = {
            "total_supply": supply,
            "total_reserves": supply,
            "chains": len(circle.get("chains", {})),
            "top_chains": {k: round(v / 1e9, 2) for k, v in top_chains},
        }

    # USD0 and USD1: use DefiLlama supply as reserve proxy
    from stake_watch.collectors.stablecoin.supply import StablecoinSupplyCollector
    try:
        supply_collector = StablecoinSupplyCollector()
        supplies = await supply_collector.collect_supply()
        for s in supplies:
            if s.token in ("USD0", "USD1"):
                token_lower = s.token.lower()
                supply_val = float(s.total_circulating)
                await store.set_setting(f"reserves.{token_lower}.total_reserves", supply_val)
                await store.set_setting(f"reserves.{token_lower}.total_supply_live", supply_val)
                await store.set_setting(f"reserves.{token_lower}.last_fetched",
                    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))
                await store.set_setting(f"reserves.{token_lower}.report_date",
                    datetime.now(timezone.utc).strftime("%Y-%m-%d"))
                issuer_info = {
                    "USD0": {"_来源": "DefiLlama (Usual Protocol, RWA 国债抵押, Chainlink PoR)", "短期国债": 100},
                    "USD1": {"_来源": "DefiLlama (World Liberty Financial, BitGo 托管, Chainlink PoR)", "国债+货币基金": 100},
                }
                await store.set_setting(f"reserves.{token_lower}.composition",
                    issuer_info.get(s.token, {}))
                results[s.token] = {
                    "total_supply": supply_val,
                    "chains": len(s.chain_breakdown),
                }
    except Exception:
        pass

    return {"success": True, "fetched": results}


@router.get("/report-config")
async def get_report_config(store: ConfigStore = Depends(get_config_store)):
    interval = await store.get_setting("stablecoin.report_interval") or 3600
    enabled = await store.get_setting("stablecoin.report_enabled")
    if enabled is None:
        enabled = True
    dex_interval = await store.get_setting("stablecoin.dex_liquidity_interval") or 300
    reserves_interval = await store.get_setting("stablecoin.reserves_fetch_interval") or 21600
    return {"interval": interval, "enabled": enabled,
            "dex_liquidity_interval": dex_interval, "reserves_fetch_interval": reserves_interval}


class ReportConfigUpdate(BaseModel):
    interval: int | None = None
    enabled: bool | None = None
    dex_liquidity_interval: int | None = None
    reserves_fetch_interval: int | None = None


@router.put("/report-config")
async def update_report_config(data: ReportConfigUpdate, store: ConfigStore = Depends(get_config_store)):
    if data.interval is not None:
        await store.set_setting("stablecoin.report_interval", data.interval)
    if data.enabled is not None:
        await store.set_setting("stablecoin.report_enabled", data.enabled)
    if data.dex_liquidity_interval is not None:
        await store.set_setting("stablecoin.dex_liquidity_interval", data.dex_liquidity_interval)
    if data.reserves_fetch_interval is not None:
        await store.set_setting("stablecoin.reserves_fetch_interval", data.reserves_fetch_interval)
    return await get_report_config(store)


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
                price_sources=p.sources,
                updated_at=datetime.now(timezone.utc),
            )
            await storage.save_stablecoin_snapshot(snap)
            results.append({
                "token": p.token, "price": p.price, "risk_level": score.level,
                "sources": [{"source": s.source, "price": s.price} for s in p.sources],
            })

        return {"success": True, "collected": results}
    except Exception as e:
        return {"success": False, "error": str(e)}
