"""DefiLlama historical APY/TVL fetcher.

DefiLlama's public API exposes per-pool history at
`https://yields.llama.fi/chart/{pool_id}` with ~daily granularity going back
to when the pool was indexed (typically months). Much longer window than our
own tvl_snapshots table can provide on a fresh install.

Two-step flow:
  1. Resolve (defillama_slug, chain, asset) → pool_id via a one-shot /pools call.
  2. Fetch that pool's chart.

pool_id resolutions are cached per protocol in AppSettings so repeat chart
requests only hit /pools when the cache is cold.
"""
from __future__ import annotations

import logging
from typing import Iterable

import httpx

from stake_watch.storage.config_store import ConfigStore

logger = logging.getLogger(__name__)

POOLS_URL = "https://yields.llama.fi/pools"
CHART_URL = "https://yields.llama.fi/chart/{pool_id}"

# Our lowercase chain codes → DefiLlama's display name
CHAIN_DISPLAY = {
    "ethereum": "Ethereum", "base": "Base",
    "solana": "Solana", "bsc": "BSC",
}


def _match_pool(pool: dict, *, slug: str, chain_display: str, asset: str,
                 pool_filter: str | None) -> bool:
    if pool.get("project") != slug:
        return False
    if pool.get("chain") != chain_display:
        return False
    symbol = (pool.get("symbol") or "").upper()
    asset_up = asset.upper()
    if pool_filter:
        # Exact symbol match (Morpho vault-style: STEAKUSDC, GTUSDCP, etc.)
        return symbol == pool_filter.upper()
    # Otherwise want a pool whose symbol IS the asset (Aave/Compound style)
    return symbol == asset_up


async def resolve_pool_id(slug: str, chain: str, asset: str,
                            pool_filter: str | None = None) -> str | None:
    """One-shot lookup: find the DefiLlama pool_id for our (protocol, chain, asset)."""
    chain_display = CHAIN_DISPLAY.get(chain.lower(), chain)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(POOLS_URL)
            resp.raise_for_status()
            data = resp.json().get("data") or []
    except Exception as e:
        logger.warning(f"DefiLlama /pools fetch failed: {e}")
        return None

    for pool in data:
        if _match_pool(pool, slug=slug, chain_display=chain_display,
                        asset=asset, pool_filter=pool_filter):
            return pool.get("pool")
    return None


async def get_cached_pool_id(store: ConfigStore, protocol_name: str,
                               chain: str, asset: str) -> str | None:
    key = f"history.pool_id.{protocol_name}.{chain.lower()}.{asset.upper()}"
    return await store.get_setting(key)


async def set_cached_pool_id(store: ConfigStore, protocol_name: str,
                               chain: str, asset: str, pool_id: str) -> None:
    key = f"history.pool_id.{protocol_name}.{chain.lower()}.{asset.upper()}"
    await store.set_setting(key, pool_id)


async def fetch_pool_chart(pool_id: str, days: int = 30) -> list[dict]:
    """Fetch DefiLlama chart data for a specific pool.

    Returns [{t, apy, tvl_usd}, ...] sorted ascending by time, filtered to
    the last `days` days. Empty list on failure.
    """
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    url = CHART_URL.format(pool_id=pool_id)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            body = resp.json()
    except Exception as e:
        logger.warning(f"DefiLlama /chart/{pool_id} fetch failed: {e}")
        return []

    raw = body.get("data") if isinstance(body, dict) else body
    if not isinstance(raw, list):
        return []

    out: list[dict] = []
    for point in raw:
        ts = point.get("timestamp")
        if not ts:
            continue
        try:
            when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, TypeError, AttributeError):
            continue
        if when < cutoff:
            continue
        apy = point.get("apy")
        tvl = point.get("tvlUsd")
        if apy is None:
            continue
        out.append({
            "t": when.isoformat(),
            "apy": float(apy),
            "tvl_usd": float(tvl) if tvl is not None else 0.0,
        })
    out.sort(key=lambda p: p["t"])
    return out


async def fetch_protocol_history(store: ConfigStore, *, protocol_name: str,
                                    slug: str, chain: str, asset: str,
                                    pool_filter: str | None,
                                    days: int) -> list[dict]:
    """Full flow: cached pool_id → chart. Populates cache on first success."""
    pool_id = await get_cached_pool_id(store, protocol_name, chain, asset)
    if not pool_id:
        pool_id = await resolve_pool_id(slug, chain, asset, pool_filter)
        if pool_id:
            try:
                await set_cached_pool_id(store, protocol_name, chain, asset, pool_id)
            except Exception as e:
                logger.warning(f"pool_id cache write failed: {e}")
    if not pool_id:
        return []
    return await fetch_pool_chart(pool_id, days=days)


def target_chain_assets(protocol_name: str, chain: str) -> Iterable[tuple[str, str]]:
    """Which (chain, asset) pairs do we want history for on this protocol?
    Default: (protocol.chain, USDC). Morpho vaults typically have their own
    single asset which the pool_filter resolves."""
    return [(chain, "USDC")]
