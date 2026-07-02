"""Morpho official historical APY/TVL — GraphQL vault historicalState.

Morpho's own indexer at https://blue-api.morpho.org/graphql exposes a
`vaultByAddress.historicalState { dailyApys, totalAssetsUsd, ... }` field
with per-day time series going back to vault inception. This is the
authoritative source for Morpho vaults (more precise than DefiLlama's
aggregation, which sometimes collapses multiple vaults under one slug).

Response shape (per Morpho schema):
    historicalState {
        dailyApys      { x: unix_ts, y: apy_decimal }    # e.g. 0.052 = 5.2%
        totalAssetsUsd { x: unix_ts, y: usd_amount }
    }
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from stake_watch.collectors.morpho.morpho_api import CHAIN_IDS, MORPHO_API_URL

logger = logging.getLogger(__name__)


async def fetch_vault_history(vault_address: str, chain: str = "base",
                                days: int = 30) -> list[dict]:
    """Return [{t, apy, tvl_usd}] sorted ascending, limited to last `days`.

    Empty list on failure or when the vault has no history yet.
    """
    chain_id = CHAIN_IDS.get(chain.lower(), 8453)
    start_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    end_ts = int(datetime.now(timezone.utc).timestamp())
    options = (f'{{ interval: DAY, startTimestamp: {start_ts}, '
                f'endTimestamp: {end_ts} }}')
    query = """
    {
      vaultByAddress(address: "%s", chainId: %d) {
        historicalState {
          dailyApys(options: %s) { x y }
          totalAssetsUsd(options: %s) { x y }
        }
      }
    }
    """ % (vault_address, chain_id, options, options)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(MORPHO_API_URL, json={"query": query})
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning(f"Morpho history fetch failed for {vault_address}: {e}")
        return []

    v = (data.get("data") or {}).get("vaultByAddress")
    if not v:
        return []
    hist = v.get("historicalState") or {}
    apys = hist.get("dailyApys") or []
    tvls = hist.get("totalAssetsUsd") or []

    # Merge by timestamp — Morpho returns two parallel series keyed by x.
    tvl_by_ts: dict[int, float] = {}
    for pt in tvls:
        try:
            tvl_by_ts[int(pt["x"])] = float(pt.get("y") or 0)
        except (KeyError, TypeError, ValueError):
            continue

    out: list[dict] = []
    for pt in apys:
        try:
            ts = int(pt["x"])
            y = pt.get("y")
            if y is None:
                continue  # missing data point — distinct from a real 0% APY
            apy_decimal = float(y)
        except (KeyError, TypeError, ValueError):
            continue
        # Morpho returns APY as decimal fraction (0.052) — normalize to %.
        apy_pct = apy_decimal * 100
        out.append({
            "t": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
            "apy": apy_pct,
            "tvl_usd": tvl_by_ts.get(ts, 0.0),
        })
    out.sort(key=lambda p: p["t"])
    return out
