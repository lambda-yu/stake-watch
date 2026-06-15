from __future__ import annotations
from datetime import datetime, timezone
import httpx
from pydantic import BaseModel

COINGECKO_TICKERS_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/tickers"
TOKEN_MAP = {"USDC": "usd-coin", "USDT": "tether"}

class CexSpread(BaseModel):
    token: str
    max_price: float
    min_price: float
    spread: float
    spread_pct: float
    num_exchanges: int
    exchanges: list[dict]
    updated_at: datetime

class CexSpreadCollector:
    async def collect_spreads(self) -> list[CexSpread]:
        results = []
        for token, coin_id in TOKEN_MAP.items():
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(COINGECKO_TICKERS_URL.format(coin_id=coin_id))
                    resp.raise_for_status()
                    data = resp.json()
                tickers = [t for t in data.get("tickers", [])
                    if not t.get("is_stale") and not t.get("is_anomaly")
                    and t.get("converted_last", {}).get("usd")]
                if not tickers:
                    continue
                prices = [(t["market"]["name"], t["converted_last"]["usd"]) for t in tickers]
                usd_prices = [p[1] for p in prices]
                max_p, min_p = max(usd_prices), min(usd_prices)
                spread = max_p - min_p
                spread_pct = (spread / min_p * 100) if min_p > 0 else 0
                results.append(CexSpread(
                    token=token, max_price=max_p, min_price=min_p,
                    spread=spread, spread_pct=spread_pct,
                    num_exchanges=len(prices),
                    exchanges=[{"name": n, "price": p} for n, p in sorted(prices, key=lambda x: x[1])[:10]],
                    updated_at=datetime.now(timezone.utc)))
            except Exception:
                continue
        return results
