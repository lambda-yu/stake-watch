from __future__ import annotations

import logging
from datetime import datetime, timezone
from statistics import median

import httpx

from stake_watch.models.stablecoin import StablecoinPrice

logger = logging.getLogger(__name__)

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
DEFILLAMA_URL = "https://stablecoins.llama.fi/stablecoins?includePrices=true"
BINANCE_URL = "https://api.binance.com/api/v3/ticker/price"
COINBASE_URL = "https://api.coinbase.com/v2/exchange-rates"
KRAKEN_URL = "https://api.kraken.com/0/public/Ticker"
OKX_URL = "https://www.okx.com/api/v5/market/ticker"


class StablecoinPriceCollector:
    async def collect_prices(self) -> list[StablecoinPrice]:
        fetchers = [
            ("CoinGecko", self._fetch_coingecko),
            ("DefiLlama", self._fetch_defillama),
            ("Binance", self._fetch_binance),
            ("Coinbase", self._fetch_coinbase),
            ("Kraken", self._fetch_kraken),
            ("OKX", self._fetch_okx),
        ]

        all_prices: dict[str, list[tuple[str, float]]] = {"USDC": [], "USDT": []}
        change_24h: dict[str, float] = {}

        for source_name, fetcher in fetchers:
            try:
                data = await fetcher()
                for token, info in data.items():
                    if token in all_prices and info.get("price"):
                        all_prices[token].append((source_name, info["price"]))
                        if "change_24h" in info and token not in change_24h:
                            change_24h[token] = info["change_24h"]
            except Exception as e:
                logger.debug(f"Price source {source_name} failed: {e}")

        results = []
        for token in ["USDC", "USDT"]:
            prices = all_prices[token]
            if not prices:
                continue
            values = [p[1] for p in prices]
            median_price = median(values)
            sources_str = ",".join(s[0] for s in prices)
            results.append(StablecoinPrice(
                token=token, price=median_price,
                deviation=abs(median_price - 1.0),
                price_24h_change=change_24h.get(token, 0.0),
                source=f"{len(prices)}源({sources_str})",
                updated_at=datetime.now(timezone.utc)))

        return results

    async def _fetch_coingecko(self) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(COINGECKO_URL, params={
                "ids": "usd-coin,tether", "vs_currencies": "usd",
                "include_24hr_change": "true"})
            resp.raise_for_status()
            data = resp.json()
        result = {}
        for token, gecko_id in [("USDC", "usd-coin"), ("USDT", "tether")]:
            if gecko_id in data:
                result[token] = {
                    "price": data[gecko_id].get("usd", 1.0),
                    "change_24h": data[gecko_id].get("usd_24h_change", 0.0)}
        return result

    async def _fetch_defillama(self) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(DEFILLAMA_URL)
            resp.raise_for_status()
            data = resp.json()
        result = {}
        for asset in data.get("peggedAssets", []):
            symbol = asset.get("symbol", "")
            if symbol in ["USDC", "USDT"]:
                price = asset.get("price")
                if price is not None:
                    result[symbol] = {"price": price}
        return result

    async def _fetch_binance(self) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(BINANCE_URL, params={"symbol": "USDCUSDT"})
            resp.raise_for_status()
            usdc_usdt = float(resp.json()["price"])
        return {"USDC": {"price": usdc_usdt}}

    async def _fetch_coinbase(self) -> dict:
        result = {}
        async with httpx.AsyncClient(timeout=10) as client:
            for token, currency in [("USDC", "USDC"), ("USDT", "USDT")]:
                resp = await client.get(COINBASE_URL, params={"currency": currency})
                resp.raise_for_status()
                usd_rate = resp.json().get("data", {}).get("rates", {}).get("USD")
                if usd_rate:
                    result[token] = {"price": float(usd_rate)}
        return result

    async def _fetch_kraken(self) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(KRAKEN_URL, params={"pair": "USDCUSD,USDTUSD"})
            resp.raise_for_status()
            data = resp.json().get("result", {})
        result = {}
        for pair_key, values in data.items():
            last = float(values["c"][0])
            if "USDC" in pair_key:
                result["USDC"] = {"price": last}
            elif "USDT" in pair_key:
                result["USDT"] = {"price": last}
        return result

    async def _fetch_okx(self) -> dict:
        result = {}
        async with httpx.AsyncClient(timeout=10) as client:
            for token, inst_id in [("USDC", "USDC-USDT")]:
                resp = await client.get(OKX_URL, params={"instId": inst_id})
                resp.raise_for_status()
                tickers = resp.json().get("data", [])
                if tickers:
                    result[token] = {"price": float(tickers[0]["last"])}
        return result
