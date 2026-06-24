"""Per-protocol-family refresh dispatchers.

Each refresher pulls latest APY/TVL from the protocol's preferred upstream
(Morpho GraphQL, Kamino REST, Aave GraphQL, etc.) and persists:
  - ProtocolStats (PoolStats list + tvl_usd) into the positions DB
  - chains breakdown JSON into the `protocols.{name}.chains` app setting

Each refresher signature:
    async def refresh_X(p, store, storage) -> dict | None

Return value: the "refreshed summary" entry the caller appends to its
response (or None if the upstream returned empty). Exceptions bubble up
to the caller so it can record them on the `failed` list.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from stake_watch.models.common import Chain
from stake_watch.models.protocol import PoolStats, ProtocolStats
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage

DEFILLAMA_CHAIN_MAP = {"base": "Base", "ethereum": "Ethereum",
                       "bsc": "BSC", "solana": "Solana"}
CHAIN_DISPLAY = {"Ethereum": "ETH", "Base": "BASE", "Solana": "SOL", "BSC": "BSC"}


def _now():
    return datetime.now(timezone.utc)


async def refresh_morpho(p, store: ConfigStore, storage: Storage) -> dict | None:
    from stake_watch.collectors.morpho.morpho_api import fetch_vault_data
    vd = await fetch_vault_data(p.vault_address, p.chain)
    if not vd:
        return None
    if vd.get("share_price_usd"):
        try:
            await storage.save_vault_share_price(p.vault_address, p.name,
                                                  vd["share_price_usd"])
        except Exception:
            pass
    tvl_d = Decimal(str(vd["tvl_usd"]))
    pool = PoolStats(pool_id=p.vault_address, asset=vd["asset"],
        supply_apy=vd["apy"], borrow_apy=0, total_supply=tvl_d,
        total_borrow=Decimal("0"), utilization=0)
    stats = ProtocolStats(chain=Chain(p.chain), protocol=p.name,
        tvl_usd=tvl_d, pools=[pool], updated_at=_now())
    await storage.save_protocol_stats(stats)

    chain_full = DEFILLAMA_CHAIN_MAP.get(p.chain, p.chain)
    chain_display = CHAIN_DISPLAY.get(chain_full, p.chain.upper())
    chains_data = [{
        "chain": chain_display, "chain_full": chain_full,
        "tvl_usd": vd["tvl_usd"], "apy": vd["apy"], "pools": 1,
        "by_asset": {vd["asset"]: {
            "tvl_usd": vd["tvl_usd"], "apy": vd["apy"], "pools": 1,
            "share_price_usd": vd.get("share_price_usd"),
        }},
    }]
    await store.set_setting(f"protocols.{p.name}.chains", chains_data)
    return {"name": p.name, "tvl_usd": vd["tvl_usd"], "apy": vd["apy"],
            "asset": vd["asset"], "pools": 1, "chains": 1, "source": "Morpho API"}


async def _refresh_from_reserves(p, store: ConfigStore, storage: Storage,
                                  reserves: list[dict], *, chain_short: str,
                                  chain_full: str, source: str,
                                  pool_id_prefix: str,
                                  asset_extra_keys: tuple[str, ...]) -> dict:
    """Shared body for Kamino/Jupiter: per-reserve list → PoolStats + chains."""
    pools = [PoolStats(
        pool_id=f"{pool_id_prefix}_{r['asset']}",
        asset=r["asset"], supply_apy=r["apy"], borrow_apy=0,
        total_supply=Decimal(str(r["tvl_usd"])),
        total_borrow=Decimal("0"), utilization=0,
    ) for r in reserves]
    total_tvl = sum((Decimal(str(r["tvl_usd"])) for r in reserves), Decimal("0"))
    stats = ProtocolStats(chain=Chain(p.chain), protocol=p.name,
        tvl_usd=total_tvl, pools=pools, updated_at=_now())
    await storage.save_protocol_stats(stats)

    by_asset = {}
    for r in reserves:
        info = {"tvl_usd": r["tvl_usd"], "apy": r["apy"], "pools": 1}
        for k in asset_extra_keys:
            if k in r:
                info[k] = r[k]
        by_asset[r["asset"]] = info
    chains_data = [{
        "chain": chain_short, "chain_full": chain_full,
        "tvl_usd": float(total_tvl),
        "apy": sum(r["apy"] for r in reserves) / len(reserves),
        "pools": len(reserves), "by_asset": by_asset,
    }]
    await store.set_setting(f"protocols.{p.name}.chains", chains_data)

    primary = next((r for r in reserves if r["asset"] == "USDC"), reserves[0])
    return {"name": p.name, "tvl_usd": float(total_tvl),
            "apy": primary["apy"], "asset": primary["asset"],
            "pools": len(reserves), "chains": 1, "source": source}


async def refresh_kamino(p, store: ConfigStore, storage: Storage) -> dict | None:
    from stake_watch.collectors.kamino.kamino_api import fetch_kamino_stable_reserves
    reserves = await fetch_kamino_stable_reserves()
    if not reserves:
        return None
    return await _refresh_from_reserves(
        p, store, storage, reserves,
        chain_short="SOL", chain_full="Solana", source="Kamino API",
        pool_id_prefix="kamino_main",
        asset_extra_keys=("utilization", "withdrawable_ratio",
                          "available_liquidity_usd"))


async def refresh_jupiter(p, store: ConfigStore, storage: Storage) -> dict | None:
    from stake_watch.collectors.jupiter.jupiter_api import (
        fetch_jupiter_lend_stable_reserves,
    )
    reserves = await fetch_jupiter_lend_stable_reserves()
    if not reserves:
        return None
    return await _refresh_from_reserves(
        p, store, storage, reserves,
        chain_short="SOL", chain_full="Solana", source="Jupiter Lend API",
        pool_id_prefix="jupiter_lend",
        asset_extra_keys=("withdrawable_ratio", "available_liquidity_usd"))


async def _refresh_from_multi_chain(p, store: ConfigStore, storage: Storage,
                                     chains_data: list[dict], *, source: str,
                                     pool_id_prefix: str) -> dict:
    """Shared body for Aave/Compound: multi-chain breakdown → primary stats."""
    primary_chain = DEFILLAMA_CHAIN_MAP.get(p.chain, p.chain)
    primary_short = CHAIN_DISPLAY.get(primary_chain, p.chain.upper())
    primary_entry = next((c for c in chains_data if c["chain"] == primary_short),
                          chains_data[0])
    pools = []
    total_tvl = Decimal("0")
    for asset, info in primary_entry.get("by_asset", {}).items():
        pools.append(PoolStats(
            pool_id=f"{pool_id_prefix}_{primary_short}_{asset}",
            asset=asset, supply_apy=info["apy"], borrow_apy=0,
            total_supply=Decimal(str(info["tvl_usd"])),
            total_borrow=Decimal("0"), utilization=0))
        total_tvl += Decimal(str(info["tvl_usd"]))
    stats = ProtocolStats(chain=Chain(p.chain), protocol=p.name,
        tvl_usd=total_tvl, pools=pools, updated_at=_now())
    await storage.save_protocol_stats(stats)
    await store.set_setting(f"protocols.{p.name}.chains", chains_data)
    primary_asset_info = (primary_entry["by_asset"].get("USDC")
                           or next(iter(primary_entry["by_asset"].values()), None))
    return {"name": p.name, "tvl_usd": float(total_tvl),
            "apy": primary_asset_info["apy"] if primary_asset_info else 0,
            "asset": "USDC" if "USDC" in primary_entry["by_asset"] else "",
            "pools": len(pools), "chains": len(chains_data), "source": source}


async def refresh_aave(p, store: ConfigStore, storage: Storage) -> dict | None:
    from stake_watch.collectors.aave.aave_api import fetch_aave_v3_stable_data
    chains_data = await fetch_aave_v3_stable_data()
    if not chains_data:
        return None
    return await _refresh_from_multi_chain(p, store, storage, chains_data,
        source="Aave V3 API", pool_id_prefix="aave_v3")


async def refresh_compound(p, store: ConfigStore, storage: Storage) -> dict | None:
    from stake_watch.collectors.compound.compound_api import (
        fetch_compound_v3_stable_data,
    )
    chains_data = await fetch_compound_v3_stable_data()
    if not chains_data:
        return None
    return await _refresh_from_multi_chain(p, store, storage, chains_data,
        source="Compound V3 API", pool_id_prefix="compound_v3")


async def refresh_sky(p, store: ConfigStore, storage: Storage) -> dict | None:
    from stake_watch.collectors.sky.sky_api import fetch_sky_susds_data
    rpc_list = await store.list_rpc()
    eth_rpc = next((r.primary_url for r in rpc_list if r.chain == "ethereum"), None)
    if not eth_rpc:
        raise RuntimeError("no ethereum RPC configured")
    sky = await fetch_sky_susds_data(eth_rpc)
    if not sky:
        return None
    tvl_d = Decimal(str(sky["tvl_usd"]))
    pool = PoolStats(pool_id="sky_susds", asset=sky["asset"],
        supply_apy=sky["apy"], borrow_apy=0, total_supply=tvl_d,
        total_borrow=Decimal("0"), utilization=0)
    stats = ProtocolStats(chain=Chain(p.chain), protocol=p.name,
        tvl_usd=tvl_d, pools=[pool], updated_at=_now())
    await storage.save_protocol_stats(stats)
    chains_data = [{
        "chain": "ETH", "chain_full": "Ethereum",
        "tvl_usd": sky["tvl_usd"], "apy": sky["apy"], "pools": 1,
        "by_asset": {sky["asset"]: {
            "apy": sky["apy"], "tvl_usd": sky["tvl_usd"], "pools": 1}},
    }]
    await store.set_setting(f"protocols.{p.name}.chains", chains_data)
    return {"name": p.name, "tvl_usd": sky["tvl_usd"], "apy": sky["apy"],
            "asset": sky["asset"], "pools": 1, "chains": 1,
            "source": "Sky on-chain (SSR)"}


# Registry: first matching predicate wins. Order matters — Morpho is checked
# before name-prefix rules because it's gated on vault_address presence.
REFRESHERS: list[tuple] = [
    ("Morpho API",
     lambda p: bool(p.vault_address) and p.chain.lower() in ("base", "ethereum"),
     refresh_morpho),
    ("Kamino API",
     lambda p: p.collector == "kamino" or p.name.startswith("kamino_"),
     refresh_kamino),
    ("Jupiter Lend API", lambda p: p.name.startswith("jupiter_"),  refresh_jupiter),
    ("Aave V3 API",      lambda p: p.name.startswith("aave_"),     refresh_aave),
    ("Compound V3 API",  lambda p: p.name.startswith("compound_"), refresh_compound),
    ("Sky on-chain",     lambda p: p.name == "sky_susds",          refresh_sky),
]


def pick_refresher(p) -> tuple[str, callable] | None:
    """Find the matching refresher for a protocol (or None for DefiLlama)."""
    for source, predicate, refresher in REFRESHERS:
        if predicate(p):
            return source, refresher
    return None
