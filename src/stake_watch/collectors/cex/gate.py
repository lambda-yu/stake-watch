"""Gate.io Uni-Loan (Simple Earn).

Public endpoint `/api/v4/earn/uni/rate` returns the current estimated
annualized rate per currency, `est_rate` as a decimal string
(e.g. "0.0161" = 1.61% APR).

The `/earn/uni/currencies/{ccy}` endpoint we tried first only returns
the user-settable min/max offer range, not the market rate — do NOT use it.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
import httpx
from stake_watch.collectors.cex.base import CexEarnCollector
from stake_watch.models.cex import CexEarnRate

URL = "https://api.gateio.ws/api/v4/earn/uni/rate"


class GateEarnCollector(CexEarnCollector):
    venue = "gate"

    async def fetch(self) -> list[CexEarnRate]:
        now = datetime.now(timezone.utc)
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(URL)
            r.raise_for_status()
            body = r.json()
        # Body is a flat list [{"currency": "USDT", "est_rate": "0.0161"}, ...]
        by_ccy = {row.get("currency"): row for row in body if isinstance(row, dict)}
        out: list[CexEarnRate] = []
        for asset in self.assets:
            entry = by_ccy.get(asset)
            if not entry:
                continue
            rate = float(entry.get("est_rate") or 0)
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