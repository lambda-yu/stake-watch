from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import httpx
from pydantic import BaseModel

GECKOTERMINAL_POOL_URL = "https://api.geckoterminal.com/api/v2/networks/{network}/pools/{address}"

MONITORED_POOLS = [
    {
        "name": "Uniswap V3 USDC/USDT",
        "network": "eth",
        "address": "0x3416cF6C708Da44DB2624D63ea0AAef7113527C6",
        "pair": "USDC/USDT",
        "dex": "Uniswap V3",
    },
    {
        "name": "Curve USDC/USDT",
        "network": "eth",
        "address": "0x4f493b7de8aac7d55f71853688b1f7c8f0243c85",
        "pair": "USDC/USDT",
        "dex": "Curve",
    },
    {
        "name": "Curve 3pool (DAI/USDC/USDT)",
        "network": "eth",
        "address": "0xbebc44782c7db0a1a60cb6fe97d0b483032ff1c7",
        "pair": "DAI/USDC/USDT",
        "dex": "Curve",
    },
    {
        "name": "Uniswap V3 USD0/USDC",
        "network": "eth",
        "address": "0x4e665157291dbcb25152ebb01061e4012f58add2",
        "pair": "USD0/USDC",
        "dex": "Uniswap V3",
    },
    {
        "name": "Curve USD0/USDC",
        "network": "eth",
        "address": "0x14100f81e33c33ecc7cdac70181fb45b6e78569f",
        "pair": "USD0/USDC",
        "dex": "Curve",
    },
    {
        "name": "Curve USD1/crv2pool",
        "network": "eth",
        "address": "0xc09e82f81cb811db0922dd48206fc2e212322caf",
        "pair": "USD1/USDC+USDT",
        "dex": "Curve",
    },
    {
        "name": "Uniswap V3 USD1/USDT",
        "network": "eth",
        "address": "0x185a1ff695d30a22c19f44c6b41e2d6d1c8c1f11",
        "pair": "USD1/USDT",
        "dex": "Uniswap V3",
    },
]



class DexPoolSnapshot(BaseModel):
    pool_name: str
    dex: str
    pair: str
    address: str
    reserve_usd: Decimal
    base_price_usd: float
    quote_price_usd: float
    price_ratio: float
    volume_24h_usd: Decimal
    volume_1h_usd: Decimal
    estimated_slippage_100k: float
    estimated_slippage_1m: float
    estimated_slippage_5m: float
    updated_at: datetime


class DexLiquidityCollector:
    async def collect_pools(self) -> list[DexPoolSnapshot]:
        results = []
        async with httpx.AsyncClient(timeout=15) as client:
            for pool in MONITORED_POOLS:
                try:
                    url = GECKOTERMINAL_POOL_URL.format(
                        network=pool["network"], address=pool["address"])
                    resp = await client.get(url)
                    resp.raise_for_status()
                    data = resp.json().get("data", {}).get("attributes", {})

                    reserve = Decimal(str(data.get("reserve_in_usd", 0) or 0))
                    base_price = float(data.get("base_token_price_usd", 0) or 0)
                    quote_price = float(data.get("quote_token_price_usd", 0) or 0)
                    ratio = base_price / quote_price if quote_price > 0 else 0

                    vol = data.get("volume_usd", {})
                    vol_24h = Decimal(str(vol.get("h24", 0) or 0))
                    vol_1h = Decimal(str(vol.get("h1", 0) or 0))

                    reserve_f = float(reserve)
                    slippage_100k = _estimate_slippage(100_000, reserve_f)
                    slippage_1m = _estimate_slippage(1_000_000, reserve_f)
                    slippage_5m = _estimate_slippage(5_000_000, reserve_f)

                    results.append(DexPoolSnapshot(
                        pool_name=pool["name"], dex=pool["dex"], pair=pool["pair"],
                        address=pool["address"], reserve_usd=reserve,
                        base_price_usd=base_price, quote_price_usd=quote_price,
                        price_ratio=ratio, volume_24h_usd=vol_24h, volume_1h_usd=vol_1h,
                        estimated_slippage_100k=slippage_100k,
                        estimated_slippage_1m=slippage_1m,
                        estimated_slippage_5m=slippage_5m,
                        updated_at=datetime.now(timezone.utc),
                    ))
                except Exception:
                    continue
        return results


def _estimate_slippage(trade_size: float, pool_tvl: float) -> float:
    """Estimate slippage as percentage using constant-product approximation.
    For concentrated liquidity (Uniswap V3), actual slippage is typically lower.
    This is a conservative upper bound."""
    if pool_tvl <= 0:
        return 100.0
    return round(trade_size / pool_tvl * 100, 4)
