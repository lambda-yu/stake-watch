"""Multi-product comparison ranking per Risk Model v2 §13.

Produces a (protocol × chain × asset) flat list with:
- raw APY, TVL
- 8-dim risk total (0-100), level (A-E)
- risk-adjusted yields (linear + exponential)
- composite selection score = adj_yield_exp × liquidity_coeff × stable_safety_coeff
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from stake_watch.api.deps import get_config_store, get_storage
from stake_watch.risk.risk_model import evaluate, ASSET_DEFAULT_STABLE
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage

router = APIRouter()


def _liquidity_coeff(tvl: float) -> float:
    """Per §13 — how comfortable can large withdrawals be?"""
    if tvl >= 1_000_000_000: return 1.00
    if tvl >= 300_000_000:   return 0.95
    if tvl >= 100_000_000:   return 0.90
    if tvl >= 30_000_000:    return 0.80
    if tvl >= 10_000_000:    return 0.65
    return 0.45


def _stable_safety_coeff(asset: str) -> float:
    """1 - stablecoin_risk_score / 100, from spec §3.6."""
    risk = ASSET_DEFAULT_STABLE.get(asset.upper(), 25)
    return 1 - risk / 100


@router.get("")
async def get_comparison(store: ConfigStore = Depends(get_config_store),
                          storage: Storage = Depends(get_storage)):
    """Return a flat ranked list of all (protocol × chain × asset) products.

    On a cold DB (no chains_breakdown setting yet), trigger one refresh pass
    so the page isn't empty for new users."""
    protos = await store.list_protocols()
    enabled = [p for p in protos if p.enabled]

    # Cold-start: if no enabled protocol has a chains_breakdown yet, run /refresh once.
    has_any_chains = False
    for p in enabled:
        if await store.get_setting(f"protocols.{p.name}.chains"):
            has_any_chains = True
            break
    if enabled and not has_any_chains:
        try:
            from stake_watch.api.routes.protocols import refresh_all_protocols
            await refresh_all_protocols(store=store, storage=storage)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"comparison cold-start refresh failed: {e}")

    # Pass 1: gather raw rows so we can compute peer-median APY per asset
    raw: list[tuple] = []  # (proto_name, chain_full, chain_short, asset, info)
    for p in protos:
        if not p.enabled:
            continue
        chains_data = await store.get_setting(f"protocols.{p.name}.chains") or []
        for entry in chains_data:
            chain_full = (entry.get("chain_full") or entry.get("chain") or p.chain).lower()
            chain_short = entry.get("chain") or chain_full.upper()
            for asset, info in (entry.get("by_asset") or {}).items():
                if asset.upper() not in ("USDC", "USDT", "USDS", "USD0", "USD1"):
                    continue
                apy = float(info.get("apy") or 0)
                tvl = float(info.get("tvl_usd") or 0)
                if apy <= 0 or tvl <= 0:
                    continue
                raw.append((p, chain_full, chain_short, asset.upper(), info, apy, tvl))

    # Peer-median APY per asset
    from statistics import median
    by_asset_apys: dict[str, list[float]] = {}
    for _, _, _, asset, _, apy, _ in raw:
        by_asset_apys.setdefault(asset, []).append(apy)
    peer_median = {a: median(v) for a, v in by_asset_apys.items() if v}

    rows: list[dict] = []
    for p, chain_full, chain_short, asset, info, apy, tvl in raw:
        signals: dict = {}
        if "utilization" in info and info["utilization"] is not None:
            signals["utilization"] = float(info["utilization"])
        if "withdrawable_ratio" in info and info["withdrawable_ratio"] is not None:
            signals["withdrawable_ratio"] = float(info["withdrawable_ratio"])
        if "supply_cap_usage" in info and info["supply_cap_usage"]:
            signals["supply_cap_usage"] = float(info["supply_cap_usage"])
        if "borrow_cap_usage" in info and info["borrow_cap_usage"]:
            signals["borrow_cap_usage"] = float(info["borrow_cap_usage"])
        borrow_apy = info.get("borrow_apy")
        if borrow_apy is not None and apy >= float(borrow_apy) > 0:
            signals["apy_inverted"] = True
        # Peer median APY premium
        if asset in peer_median:
            signals["apy_premium_pct"] = apy - peer_median[asset]
        # TVL 7d trend
        tvl_7d_ago = await storage.get_tvl_n_days_ago(p.name, chain_full, asset, 7)
        if tvl_7d_ago and tvl_7d_ago > 0:
            drop = max(0, (tvl_7d_ago - tvl) / tvl_7d_ago)
            if drop > 0.05:
                signals["tvl_drop_24h"] = drop  # use spec 24h thresholds for 7d too

        r = evaluate(p.name, chain_full, asset, apy, live_signals=signals or None)
        liq = _liquidity_coeff(tvl)
        stab = _stable_safety_coeff(asset)
        composite = r.adjusted_yield_exp * liq * stab
        rows.append({
            "protocol": p.name,
            "protocol_type": getattr(p, "protocol_type", None),
            "chain_full": chain_full,
            "chain": chain_short,
            "asset": asset,
            "apy": apy,
            "tvl_usd": tvl,
            "utilization": signals.get("utilization"),
            "withdrawable_ratio": signals.get("withdrawable_ratio"),
            "supply_cap_usage": signals.get("supply_cap_usage"),
            "borrow_cap_usage": signals.get("borrow_cap_usage"),
            "apy_inverted": bool(signals.get("apy_inverted")),
            "apy_premium_pct": signals.get("apy_premium_pct"),
            "tvl_drop_7d": signals.get("tvl_drop_24h"),
            "borrow_apy": borrow_apy,
            "risk_total": r.total,
            "risk_level": r.level,
            "adjusted_yield_linear": r.adjusted_yield_linear,
            "adjusted_yield_exp": r.adjusted_yield_exp,
            "liquidity_coeff": round(liq, 3),
            "stable_safety_coeff": round(stab, 3),
            "composite_score": round(composite, 4),
            "has_live_signals": bool(signals),
        })

    rows.sort(key=lambda x: -x["composite_score"])
    return {"rows": rows, "count": len(rows),
            "peer_median_apy": {a: round(v, 3) for a, v in peer_median.items()}}


@router.post("/send-telegram")
async def send_telegram_screenshot(storage: Storage = Depends(get_storage)):
    """Capture the /comparison page from the configured frontend URL and
    push as a Telegram photo. Returns {"success": bool, "error"?: str}."""
    from stake_watch.alerts.comparison_screenshot import send_comparison_screenshot
    return await send_comparison_screenshot(storage)


class ScreenshotConfig(BaseModel):
    frontend_url: str | None = None


@router.get("/screenshot-config")
async def get_screenshot_config(store: ConfigStore = Depends(get_config_store)):
    url = await store.get_setting("screenshot.frontend_url") or "http://localhost:5173"
    return {"frontend_url": url}


@router.put("/screenshot-config")
async def update_screenshot_config(data: ScreenshotConfig,
                                     store: ConfigStore = Depends(get_config_store)):
    if data.frontend_url is not None:
        await store.set_setting("screenshot.frontend_url", data.frontend_url.rstrip("/"))
    return await get_screenshot_config(store)
