"""Bybit flexible savings.

Public endpoint. Rates in percent-string form ("1.52%"). Tiered products
expose `tierAprDetails[]` with per-tier `estimateApr`.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
import httpx
from stake_watch.collectors.cex.base import CexEarnCollector
from stake_watch.models.cex import CexEarnRate

URL = "https://api.bybit.com/v5/earn/product?category=FlexibleSaving&coin={coin}"


def _pct_to_decimal(s: str) -> float:
    return float(s.rstrip("%")) / 100.0


class BybitEarnCollector(CexEarnCollector):
    venue = "bybit"

    async def fetch(self) -> list[CexEarnRate]:
        now = datetime.now(timezone.utc)
        out: list[CexEarnRate] = []
        async with httpx.AsyncClient(timeout=20) as c:
            for asset in self.assets:
                r = await c.get(URL.format(coin=asset))
                r.raise_for_status()
                body = r.json()
                if body.get("retCode") != 0:
                    continue
                items = ((body.get("result") or {}).get("list")) or []
                # Prefer the "Available" flexible product for this coin
                pick = next((p for p in items if p.get("coin") == asset
                             and p.get("category") == "FlexibleSaving"), None)
                if pick is None:
                    continue
                tiers = pick.get("tierAprDetails") or []
                if tiers:
                    rates = [_pct_to_decimal(t["estimateApr"]) for t in tiers if t.get("estimateApr")]
                    apy_min, apy_max = (min(rates), max(rates)) if rates else (0.0, 0.0)
                    tier_note = "; ".join(
                        f'{t.get("min","?")}-{t.get("max","?")}: {t.get("estimateApr","?")}'
                        for t in tiers)
                else:
                    apy_min = apy_max = _pct_to_decimal(pick.get("estimateApr", "0%"))
                    tier_note = None
                if apy_max <= 0:
                    continue
                out.append(CexEarnRate(
                    venue=self.venue, asset=asset,
                    apy_min=apy_min, apy_max=apy_max,
                    tier_note=tier_note,
                    raw_json=json.dumps(pick),
                    updated_at=now,
                ))
        return out