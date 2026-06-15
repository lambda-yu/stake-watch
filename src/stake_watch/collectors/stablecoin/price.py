from __future__ import annotations
from datetime import datetime, timezone
import httpx
from stake_watch.models.stablecoin import StablecoinPrice

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_IDS = {"USDC": "usd-coin", "USDT": "tether"}

DEFILLAMA_URL = "https://stablecoins.llama.fi/stablecoins?includePrices=true"
DEFILLAMA_SYMBOLS = {"USDC": "USD Coin", "USDT": "Tether"}

class StablecoinPriceCollector:
    async def collect_prices(self) -> list[StablecoinPrice]:
        results = []
        cg_prices = await self._fetch_coingecko()
        dl_prices = await self._fetch_defillama()

        for token in ["USDC", "USDT"]:
            sources = []
            if token in cg_prices:
                sources.append(cg_prices[token])
            if token in dl_prices:
                sources.append(dl_prices[token])
            if not sources:
                continue
            # Use median price
            prices = sorted([s["price"] for s in sources])
            median_price = prices[len(prices) // 2]
            change_24h = sources[0].get("change_24h", 0.0)
            results.append(StablecoinPrice(
                token=token, price=median_price,
                deviation=abs(median_price - 1.0),
                price_24h_change=change_24h,
                source="multi",
                updated_at=datetime.now(timezone.utc)))
        return results

    async def _fetch_coingecko(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(COINGECKO_URL, params={
                    "ids": "usd-coin,tether", "vs_currencies": "usd",
                    "include_24hr_change": "true"})
                resp.raise_for_status()
                data = resp.json()
            result = {}
            for token, gecko_id in COINGECKO_IDS.items():
                if gecko_id in data:
                    result[token] = {
                        "price": data[gecko_id].get("usd", 1.0),
                        "change_24h": data[gecko_id].get("usd_24h_change", 0.0)}
            return result
        except Exception:
            return {}

    async def _fetch_defillama(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(DEFILLAMA_URL)
                resp.raise_for_status()
                data = resp.json()
            result = {}
            for asset in data.get("peggedAssets", []):
                name = asset.get("name", "")
                symbol = asset.get("symbol", "")
                if symbol in ["USDC", "USDT"]:
                    price = asset.get("price")
                    if price is not None:
                        result[symbol] = {"price": price, "change_24h": 0.0}
            return result
        except Exception:
            return {}
