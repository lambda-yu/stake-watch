"""Periodic TVL / vault-share-price snapshot writer for trend signals.

`refresh_all_protocols()` produces the latest chains breakdown per protocol;
this module persists time-series snapshots of (protocol, chain, asset, tvl, apy)
and Morpho vault share prices so the risk model can detect drops vs N hours/days
ago.

The same write routine runs in two places:
- inline at the end of `/refresh` (so manual refreshes leave a fresh point)
- as a scheduled job (so trend data accumulates without user intervention)
"""
from __future__ import annotations

import logging

from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage

logger = logging.getLogger(__name__)


async def write_tvl_snapshots_from_settings(store: ConfigStore,
                                              storage: Storage,
                                              names: list[str] | None = None) -> int:
    """Read `protocols.{name}.chains` for each enabled protocol and persist
    one tvl_snapshot row per (chain, asset). Returns the row count.

    If `names` is given, only those protocols are processed.
    """
    protos = await store.list_protocols()
    written = 0
    for p in protos:
        if not p.enabled:
            continue
        if names is not None and p.name not in names:
            continue
        chains_data = await store.get_setting(f"protocols.{p.name}.chains") or []
        for entry in chains_data:
            chain_full = (entry.get("chain_full") or entry.get("chain") or "").lower()
            for asset, info in (entry.get("by_asset") or {}).items():
                tvl = float(info.get("tvl_usd") or 0)
                apy = float(info.get("apy") or 0)
                if tvl <= 0:
                    continue
                try:
                    await storage.save_tvl_snapshot(p.name, chain_full,
                                                     asset.upper(), tvl, apy)
                    written += 1
                except Exception as e:
                    logger.warning(f"tvl snapshot write failed for "
                                    f"{p.name}/{chain_full}/{asset}: {e}")
    return written


async def write_vault_share_price_snapshots(store: ConfigStore,
                                              storage: Storage) -> int:
    """Pull current vault share price for each Morpho protocol and persist."""
    from stake_watch.collectors.morpho.morpho_api import fetch_vault_data
    protos = await store.list_protocols()
    written = 0
    for p in protos:
        if not p.enabled or not getattr(p, "vault_address", None):
            continue
        if p.chain.lower() not in ("base", "ethereum"):
            continue
        try:
            vd = await fetch_vault_data(p.vault_address, p.chain)
            if vd and vd.get("share_price_usd"):
                await storage.save_vault_share_price(p.vault_address, p.name,
                                                     vd["share_price_usd"])
                written += 1
        except Exception as e:
            logger.warning(f"share-price snapshot failed for {p.name}: {e}")
    return written
