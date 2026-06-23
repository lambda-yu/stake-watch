"""Kamino Lend official REST API client.

Docs: https://api.kamino.finance/documentation/
"""
from __future__ import annotations

import httpx

MAIN_MARKET = "7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF"
METRICS_URL = f"https://api.kamino.finance/kamino-market/{MAIN_MARKET}/reserves/metrics"


async def fetch_kamino_stable_reserves() -> list[dict]:
    """Return USDC/USDT reserves from the Kamino main market.

    Each entry: {asset, apy (%), tvl_usd}
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(METRICS_URL)
        resp.raise_for_status()
        data = resp.json()

    result: list[dict] = []
    for r in data:
        token = (r.get("liquidityToken") or "").upper()
        if token not in ("USDC", "USDT"):
            continue
        try:
            apy = float(r.get("supplyApy", 0)) * 100
            tvl = float(r.get("totalSupplyUsd", 0))
            borrow_usd = float(r.get("totalBorrowUsd", 0))
            util = (borrow_usd / tvl) if tvl > 0 else 0
            avail_usd = max(0.0, tvl - borrow_usd)
            withdrawable_ratio = (avail_usd / tvl) if tvl > 0 else 0
        except (TypeError, ValueError):
            continue
        result.append({
            "asset": token, "apy": apy, "tvl_usd": tvl,
            "utilization": util,
            "withdrawable_ratio": withdrawable_ratio,
            "available_liquidity_usd": avail_usd,
        })
    return result
