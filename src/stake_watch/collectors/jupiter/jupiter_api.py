"""Jupiter Lend official REST API client.

Docs: https://developers.jup.ag/docs/api-reference/lend
"""
from __future__ import annotations

import httpx

TOKENS_URL = "https://api.jup.ag/lend/v1/earn/tokens"


async def fetch_jupiter_lend_stable_reserves() -> list[dict]:
    """Return USDC/USDT reserves from Jupiter Lend.

    Each entry: {asset, apy (%), tvl_usd}
    Rate is `totalRate` in basis points (484 = 4.84%).
    TVL = totalAssets / 10^decimals * asset.price.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(TOKENS_URL)
        resp.raise_for_status()
        data = resp.json()

    result: list[dict] = []
    for t in data:
        asset_info = t.get("asset") or {}
        symbol = (asset_info.get("symbol") or "").upper()
        if symbol not in ("USDC", "USDT"):
            continue
        try:
            decimals = int(asset_info.get("decimals", 6))
            price = float(asset_info.get("price", 0))
            total_assets = int(t.get("totalAssets", 0))
            apy_bps = int(t.get("totalRate", 0))
        except (TypeError, ValueError):
            continue
        tvl_usd = total_assets / (10 ** decimals) * price
        # Liquidity layer withdrawal headroom (current available right now)
        ls = t.get("liquiditySupplyData") or {}
        try:
            supply_raw = int(ls.get("supply", 0))
            withdrawable_raw = int(ls.get("withdrawable", 0))
            withdrawable_ratio = (withdrawable_raw / supply_raw) if supply_raw > 0 else 0
            withdrawable_usd = withdrawable_raw / (10 ** decimals) * price
        except (TypeError, ValueError):
            withdrawable_ratio = 0
            withdrawable_usd = 0
        result.append({
            "asset": symbol, "apy": apy_bps / 100, "tvl_usd": tvl_usd,
            "withdrawable_ratio": withdrawable_ratio,
            "available_liquidity_usd": withdrawable_usd,
            "utilization": max(0.0, 1.0 - withdrawable_ratio),
        })
    return result
