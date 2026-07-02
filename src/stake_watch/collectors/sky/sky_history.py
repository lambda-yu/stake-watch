"""Sky sUSDS official historical SSR.

Sky's own dashboard (sky.money / makerburn) pulls historical Sky Savings Rate
data from Block Analitica's public API:
    https://info-sky.blockanalitica.com/api/v1/savings-rate/

This is a third-party operator but is Sky's officially-sanctioned indexer —
what the Sky protocol frontend itself displays. No API key required.

Response shape (documented via the dashboard's dev-tools calls):
    [
      {"date": "2026-06-30", "rate": "0.055", "tvl": "9200000000"},
      ...
    ]
where `rate` is the SSR expressed as an annualised decimal (5.5% → "0.055").
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

# Block Analitica's Sky endpoints (used by info.sky.money's charts).
BLOCK_ANALITICA_BASE = "https://info-sky.blockanalitica.com/api/v1"
CANDIDATE_PATHS = [
    "/susds/rates/history/",
    "/savings-rate/",
    "/savings-rates/",
]


def _parse_date(raw) -> datetime | None:
    if raw is None:
        return None
    try:
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        s = str(raw)
        if len(s) == 10 and s.count("-") == 2:
            return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


async def _try_endpoint(path: str) -> list[dict]:
    url = BLOCK_ANALITICA_BASE + path
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            body = resp.json()
    except Exception as e:
        logger.debug(f"Sky history candidate {path} failed: {e}")
        return []

    # Response may be plain list or wrapped in {results: [...]}.
    if isinstance(body, dict):
        body = body.get("results") or body.get("data") or body.get("history") or []
    if not isinstance(body, list):
        return []
    return body


async def fetch_ssr_history(days: int = 30) -> list[dict]:
    """Return [{t, apy, tvl_usd}] sorted ascending, filtered to last `days`.

    Empty list if no responsive endpoint or vault has no history.
    """
    raw: list[dict] = []
    for path in CANDIDATE_PATHS:
        raw = await _try_endpoint(path)
        if raw:
            break
    if not raw:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out: list[dict] = []
    for pt in raw:
        when = _parse_date(pt.get("date") or pt.get("timestamp"))
        if not when:
            continue
        if when < cutoff:
            continue
        rate_raw = (pt.get("rate") or pt.get("ssr") or pt.get("apy")
                     or pt.get("value"))
        if rate_raw is None:
            continue
        try:
            rate_dec = float(rate_raw)
        except (TypeError, ValueError):
            continue
        # Rate encoded as decimal (0.055 = 5.5%) → percent.
        apy_pct = rate_dec * 100 if rate_dec < 1.0 else rate_dec
        tvl_raw = pt.get("tvl") or pt.get("totalSupply") or pt.get("total_assets")
        try:
            tvl_usd = float(tvl_raw) if tvl_raw is not None else 0.0
        except (TypeError, ValueError):
            tvl_usd = 0.0
        out.append({"t": when.isoformat(), "apy": apy_pct, "tvl_usd": tvl_usd})
    out.sort(key=lambda p: p["t"])
    return out
