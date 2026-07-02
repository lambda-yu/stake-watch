"""Kamino official historical APY/TVL.

Kamino's public REST API at https://api.kamino.finance/ exposes per-reserve
history at:
    /kamino-market/{market}/reserves/{reserve_mint}/metrics/history
        ?start={unix}&end={unix}&frequency=hour|day

Response is a list of samples:
    [{"timestamp": ISO8601, "metrics": {"supplyApy": 0.052,
      "totalSupplyUsd": 1_000_000, ...}}, ...]

The exact keys inside `metrics` vary slightly across API versions; the
parser is tolerant and looks up several known aliases.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from stake_watch.collectors.kamino.kamino_api import MAIN_MARKET

logger = logging.getLogger(__name__)

# Mint addresses on Solana mainnet
ASSET_MINTS = {
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
}

HISTORY_URL_TMPL = (
    "https://api.kamino.finance/kamino-market/{market}/reserves/"
    "{mint}/metrics/history"
)


def _extract_apy(metrics: dict) -> float | None:
    for k in ("supplyApy", "supply_apy", "supplyAPY"):
        v = metrics.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def _extract_tvl(metrics: dict) -> float:
    for k in ("totalSupplyUsd", "total_supply_usd", "totalSupply",
               "supplyLiquidityUsd"):
        v = metrics.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return 0.0


async def fetch_reserve_history(asset: str, days: int = 30,
                                  market: str = MAIN_MARKET) -> list[dict]:
    """Return [{t, apy, tvl_usd}] for a Kamino reserve, sorted ascending.

    APY is normalized to percent (Kamino returns decimals like 0.052).
    """
    mint = ASSET_MINTS.get(asset.upper())
    if not mint:
        return []
    start = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    end = int(datetime.now(timezone.utc).timestamp())
    freq = "day" if days > 3 else "hour"
    url = HISTORY_URL_TMPL.format(market=market, mint=mint)
    params = {"start": start, "end": end, "frequency": freq}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            body = resp.json()
    except Exception as e:
        logger.warning(f"Kamino history fetch failed for {asset}: {e}")
        return []

    # Response is usually a plain list of {timestamp, metrics: {...}}.
    if isinstance(body, dict):
        body = body.get("history") or body.get("data") or []
    if not isinstance(body, list):
        return []

    out: list[dict] = []
    for point in body:
        ts_raw = point.get("timestamp") or point.get("createdAt")
        if not ts_raw:
            continue
        try:
            if isinstance(ts_raw, (int, float)):
                when = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
            else:
                when = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        metrics = point.get("metrics") if isinstance(point.get("metrics"), dict) else point
        apy_dec = _extract_apy(metrics)
        if apy_dec is None:
            continue
        out.append({
            "t": when.isoformat(),
            "apy": apy_dec * 100,  # decimal → percent
            "tvl_usd": _extract_tvl(metrics),
        })
    out.sort(key=lambda p: p["t"])
    return out
