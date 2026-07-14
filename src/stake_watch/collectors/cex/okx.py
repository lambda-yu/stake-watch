"""OKX flexible savings (lending-rate-summary).

Public endpoint. Returns a single rate per currency; no tiering.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
import httpx
from stake_watch.collectors.cex.base import CexEarnCollector
from stake_watch.models.cex import CexEarnRate

URL = "https://www.okx.com/api/v5/finance/savings/lending-rate-summary?ccy={ccy}"


class OkxEarnCollector(CexEarnCollector):
    venue = "okx"

    async def fetch(self) -> list[CexEarnRate]:
        now = datetime.now(timezone.utc)
        out: list[CexEarnRate] = []
        async with httpx.AsyncClient(timeout=20) as c:
            for asset in self.assets:
                r = await c.get(URL.format(ccy=asset))
                r.raise_for_status()
                body = r.json()
                # {"code":"0","data":[{"ccy":"USDT","estRate":"0.025",...}]}
                entry = (body.get("data") or [{}])[0]
                rate = float(entry.get("estRate") or 0)
                if rate <= 0:
                    continue
                out.append(CexEarnRate(
                    venue=self.venue, asset=asset,
                    apy_min=rate, apy_max=rate,
                    tier_note=None,
                    raw_json=json.dumps(entry),
                    updated_at=now,
                ))
        return out