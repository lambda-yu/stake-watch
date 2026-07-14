"""Gate.io Uni-Loan (Simple Earn).

Public endpoint. Returns hourly `min_rate`/`max_rate` per currency;
we annualize (rate * 24 * 365) to produce APR.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
import httpx
from stake_watch.collectors.cex.base import CexEarnCollector
from stake_watch.models.cex import CexEarnRate

URL = "https://api.gateio.ws/api/v4/earn/uni/currencies/{ccy}"
HOURS_PER_YEAR = 24 * 365


class GateEarnCollector(CexEarnCollector):
    venue = "gate"

    async def fetch(self) -> list[CexEarnRate]:
        now = datetime.now(timezone.utc)
        out: list[CexEarnRate] = []
        async with httpx.AsyncClient(timeout=20) as c:
            for asset in self.assets:
                r = await c.get(URL.format(ccy=asset))
                if r.status_code != 200:
                    continue
                body = r.json()
                min_r = float(body.get("min_rate") or 0)
                max_r = float(body.get("max_rate") or 0)
                if max_r <= 0:
                    continue
                # Gate returns hourly rates; annualize to APR
                apy_min = min_r * HOURS_PER_YEAR
                apy_max = max_r * HOURS_PER_YEAR
                tier_note = (f"hourly {min_r:.8f}–{max_r:.8f}"
                             if apy_min != apy_max else None)
                out.append(CexEarnRate(
                    venue=self.venue, asset=asset,
                    apy_min=apy_min, apy_max=apy_max,
                    tier_note=tier_note,
                    raw_json=json.dumps(body),
                    updated_at=now,
                ))
        return out