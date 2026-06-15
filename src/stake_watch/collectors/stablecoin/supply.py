from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
import httpx
from stake_watch.models.stablecoin import ChainSupply, StablecoinSupply

DEFILLAMA_URL = "https://stablecoins.llama.fi/stablecoins?includePrices=true"

class StablecoinSupplyCollector:
    async def collect_supply(self) -> list[StablecoinSupply]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(DEFILLAMA_URL)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []

        results = []
        for asset in data.get("peggedAssets", []):
            symbol = asset.get("symbol", "")
            if symbol not in ("USDC", "USDT", "USD0", "USD1"):
                continue

            total = Decimal(str(asset.get("circulating", {}).get("peggedUSD", 0)))
            prev_day = Decimal(str(asset.get("circulatingPrevDay", {}).get("peggedUSD", 0)))
            prev_week = Decimal(str(asset.get("circulatingPrevWeek", {}).get("peggedUSD", 0)))

            change_24h = total - prev_day
            change_24h_pct = float(change_24h / prev_day * 100) if prev_day > 0 else 0.0
            change_7d_pct = float((total - prev_week) / prev_week * 100) if prev_week > 0 else 0.0

            chains = []
            for chain_name, chain_data in asset.get("chainCirculating", {}).items():
                current = chain_data.get("current", {}).get("peggedUSD", 0)
                pd = chain_data.get("circulatingPrevDay", {}).get("peggedUSD", 0)
                if current > 0:
                    c_dec = Decimal(str(current))
                    pd_dec = Decimal(str(pd)) if pd else c_dec
                    ch_pct = float((c_dec - pd_dec) / pd_dec * 100) if pd_dec > 0 else 0.0
                    chains.append(ChainSupply(chain=chain_name, circulating=c_dec,
                        prev_day=pd_dec, change_24h_pct=ch_pct))

            chains.sort(key=lambda x: x.circulating, reverse=True)

            results.append(StablecoinSupply(
                token=symbol, total_circulating=total,
                chain_breakdown=chains[:10],  # Top 10 chains
                net_change_24h=change_24h, net_change_24h_pct=change_24h_pct,
                net_change_7d_pct=change_7d_pct,
                updated_at=datetime.now(timezone.utc)))

        return results
