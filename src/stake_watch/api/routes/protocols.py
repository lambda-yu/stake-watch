import json
from decimal import Decimal
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from stake_watch.api.deps import get_config_store, get_storage
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage

router = APIRouter()

class ProtocolCreate(BaseModel):
    name: str
    chain: str
    collector: str
    enabled: bool = True
    safety_rank: int | None = None
    safety_score: float | None = None
    reference_apy: str | None = None
    primary_risks: list[str] = []
    vault_address: str | None = None
    defillama_slug: str | None = None
    pool_filter: str | None = None
    protocol_type: str | None = None

def _classify(name: str) -> str:
    n = name.lower()
    if n.startswith("morpho_"):
        return "vault"
    if n == "sky_susds" or "savings" in n:
        return "savings"
    return "lending"


# Primary (chain, asset) for each protocol — drives the protocol-level risk summary.
PRIMARY_PRODUCT: dict[str, tuple[str, str]] = {
    "aave_v3_base":               ("base",     "USDC"),
    "sky_susds":                  ("ethereum", "USDS"),
    "compound_v3_usdc":           ("base",     "USDC"),
    "morpho_steakhouse_usdc":     ("base",     "USDC"),
    "morpho_gauntlet_usdc_prime": ("base",     "USDC"),
    "morpho_pangolins_usdc":      ("base",     "USDC"),
    "morpho_gauntlet_rwa_usdc":   ("ethereum", "USDC"),
    "fluid_usdc":                 ("ethereum", "USDC"),
    "jupiter_lend":               ("solana",   "USDC"),
    "kamino_usdc":                ("solana",   "USDC"),
}


def _to_dict(p):
    from stake_watch.risk.risk_model import evaluate, DIM_LABELS, DIMENSIONS
    chain, asset = PRIMARY_PRODUCT.get(p.name, (p.chain, "USDC"))
    risk = evaluate(p.name, chain, asset, None)
    risk_dimensions = [
        {"key": k, "label": DIM_LABELS[k], "weight": w,
         "score": risk.dimensions[k]["score"],
         "notes": risk.dimensions[k]["notes"],
         "source": risk.dimensions[k].get("source", "curated")}
        for k, _, w in DIMENSIONS
    ]
    from datetime import datetime, timezone
    return {"id": p.id, "name": p.name, "chain": p.chain, "collector": p.collector,
        "enabled": p.enabled, "safety_rank": p.safety_rank, "safety_score": p.safety_score,
        "reference_apy": p.reference_apy, "primary_risks": json.loads(p.primary_risks) if p.primary_risks else [],
        "vault_address": p.vault_address, "defillama_slug": p.defillama_slug,
        "pool_filter": getattr(p, "pool_filter", None),
        "protocol_type": getattr(p, "protocol_type", None) or _classify(p.name),
        "primary_chain": chain, "primary_asset": asset,
        "risk_total": risk.total,
        "risk_level": risk.level,
        "risk_dimensions": risk_dimensions,
        "risk_evaluated_at": datetime.now(timezone.utc).isoformat()}


async def _enrich_with_stats(protocol_dict: dict, storage: Storage) -> dict:
    stats = await storage.get_latest_protocol_stats(protocol_dict["name"])
    if stats and stats.pools:
        tvl = float(stats.tvl_usd)
        usdc_pool = next((p for p in stats.pools if "USDC" in p.asset.upper()), None)
        usdt_pool = next((p for p in stats.pools if "USDT" in p.asset.upper()), None)
        susds_pool = next((p for p in stats.pools if "SUSDS" in p.asset.upper() or "USDS" in p.asset.upper()), None)
        default_pool = usdc_pool or usdt_pool or susds_pool or stats.pools[0]
        protocol_dict["live_tvl_usd"] = tvl
        protocol_dict["live_apy"] = default_pool.supply_apy
        protocol_dict["live_pool_asset"] = default_pool.asset
        protocol_dict["stats_updated_at"] = stats.updated_at.isoformat()
        protocol_dict["usdc_apy"] = usdc_pool.supply_apy if usdc_pool else None
        protocol_dict["usdc_tvl"] = float(usdc_pool.total_supply) if usdc_pool else None
        protocol_dict["usdt_apy"] = usdt_pool.supply_apy if usdt_pool else None
        protocol_dict["usdt_tvl"] = float(usdt_pool.total_supply) if usdt_pool else None
        if susds_pool and not usdc_pool and not usdt_pool:
            protocol_dict["primary_asset"] = susds_pool.asset
            protocol_dict["primary_asset_apy"] = susds_pool.supply_apy
            protocol_dict["primary_asset_tvl"] = float(susds_pool.total_supply)
    else:
        protocol_dict["live_tvl_usd"] = None
        protocol_dict["live_apy"] = None
        protocol_dict["usdc_apy"] = None
        protocol_dict["usdt_apy"] = None
    return protocol_dict


MONITORED_CHAINS = ["Ethereum", "Base", "Solana", "BSC"]
CHAIN_DISPLAY = {"Ethereum": "ETH", "Base": "BASE", "Solana": "SOL", "BSC": "BSC"}


async def _fetch_multi_chain_data(defillama_slug: str, pool_filter: str | None = None) -> list[dict]:
    """Fetch USDC + USDT pool data across all monitored chains for a given slug."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://yields.llama.fi/pools")
            resp.raise_for_status()
            data = resp.json().get("data", [])
    except Exception:
        return []

    by_chain_asset: dict[tuple[str, str], list[dict]] = {}
    for p in data:
        if p.get("project") != defillama_slug:
            continue
        chain = p.get("chain", "")
        if chain not in MONITORED_CHAINS:
            continue
        symbol = (p.get("symbol") or "").upper()
        if pool_filter and pool_filter.upper() not in symbol:
            continue
        asset = None
        if "USDC" in symbol:
            asset = "USDC"
        elif "USDT" in symbol:
            asset = "USDT"
        elif "SUSDS" in symbol or "USDS" in symbol:
            asset = "USDS"
        elif "DAI" in symbol:
            asset = "DAI"
        if not pool_filter and not asset:
            continue
        by_chain_asset.setdefault((chain, asset or "Other"), []).append(p)

    result = []
    chains_seen: dict[str, dict] = {}
    for (chain, asset), pools in by_chain_asset.items():
        tvl = sum(float(p.get("tvlUsd", 0) or 0) for p in pools)
        apys = [p.get("apy", 0) or 0 for p in pools if p.get("apy")]
        avg_apy = sum(apys) / len(apys) if apys else 0
        entry = chains_seen.setdefault(chain, {
            "chain": CHAIN_DISPLAY.get(chain, chain),
            "chain_full": chain,
            "tvl_usd": 0,
            "apy": 0,
            "pools": 0,
            "by_asset": {},
        })
        entry["tvl_usd"] += tvl
        entry["pools"] += len(pools)
        entry["by_asset"][asset] = {"tvl_usd": tvl, "apy": avg_apy, "pools": len(pools)}

    for entry in chains_seen.values():
        usdc = entry["by_asset"].get("USDC")
        usdt = entry["by_asset"].get("USDT")
        if usdc and usdt:
            entry["apy"] = (usdc["apy"] + usdt["apy"]) / 2
        elif usdc:
            entry["apy"] = usdc["apy"]
        elif usdt:
            entry["apy"] = usdt["apy"]
        result.append(entry)

    result.sort(key=lambda x: -x["tvl_usd"])
    return result


@router.get("")
async def list_protocols(store: ConfigStore = Depends(get_config_store),
                          storage: Storage = Depends(get_storage)):
    protos = await store.list_protocols()
    enriched = []
    for p in protos:
        d = _to_dict(p)
        d = await _enrich_with_stats(d, storage)
        chains_data = await store.get_setting(f"protocols.{p.name}.chains")
        if chains_data:
            d["chains_breakdown"] = chains_data
        enriched.append(d)
    return enriched


@router.get("/{protocol_id}/chains")
async def get_protocol_chains(protocol_id: int,
                                store: ConfigStore = Depends(get_config_store)):
    """Fetch and return live multi-chain breakdown for a protocol."""
    p = await store.get_protocol(protocol_id)
    if not p:
        return {"error": "not found"}
    slug = p.defillama_slug
    if not slug:
        return {"chains": []}
    pool_filter = getattr(p, "pool_filter", None)
    chains = await _fetch_multi_chain_data(slug, pool_filter)
    await store.set_setting(f"protocols.{p.name}.chains", chains)
    return {"chains": chains, "protocol": p.name}

@router.post("", status_code=201)
async def add_protocol(data: ProtocolCreate, store: ConfigStore = Depends(get_config_store)):
    p = await store.add_protocol(**data.model_dump())
    return _to_dict(p)

@router.patch("/{protocol_id}/toggle")
async def toggle_protocol(protocol_id: int, store: ConfigStore = Depends(get_config_store)):
    await store.toggle_protocol(protocol_id)
    p = await store.get_protocol(protocol_id)
    return _to_dict(p)


class RiskScoresUpdate(BaseModel):
    contract: float | None = None
    market: float | None = None
    liquidity: float | None = None
    collateral_oracle: float | None = None
    governance: float | None = None
    stablecoin: float | None = None
    chain: float | None = None
    yield_: float | None = None


@router.post("/{protocol_id}/evaluate")
async def reevaluate_protocol(protocol_id: int,
                              store: ConfigStore = Depends(get_config_store),
                              storage: Storage = Depends(get_storage)):
    """Re-pull live data for this protocol and return fresh evaluation."""
    p = await store.get_protocol(protocol_id)
    if not p:
        return Response(status_code=404)
    try:
        await refresh_all_protocols(name_filter=p.name, store=store, storage=storage)
    except Exception:
        pass  # fall back to cached data
    p = await store.get_protocol(protocol_id)
    return _to_dict(p)


@router.get("/{protocol_id}/risk-status")
async def get_protocol_risk_status(protocol_id: int,
                                    refresh: bool = False,
                                    store: ConfigStore = Depends(get_config_store),
                                    storage: Storage = Depends(get_storage)):
    """Return live operational risk-control status for a protocol.

    Pass `?refresh=true` to first re-pull this protocol's official data."""
    p = await store.get_protocol(protocol_id)
    if not p:
        return Response(status_code=404)
    if refresh:
        try:
            await refresh_all_protocols(name_filter=p.name, store=store, storage=storage)
        except Exception:
            pass
        p = await store.get_protocol(protocol_id)
    from stake_watch.risk.protocol_status import evaluate_protocol_status
    result = await evaluate_protocol_status(p.name, storage, store)
    return result or {"score": 0, "level": "critical", "checks": [], "updated_at": None}

@router.delete("/{protocol_id}", status_code=204)
async def delete_protocol(protocol_id: int, store: ConfigStore = Depends(get_config_store)):
    await store.delete_protocol(protocol_id)
    return Response(status_code=204)


@router.post("/fix-vault-addresses")
async def fix_vault_addresses(store: ConfigStore = Depends(get_config_store)):
    """One-shot: update known vault addresses for protocols missing them.

    Used when seed.yaml was updated after first DB initialization."""
    VAULT_ADDRESSES = {
        "morpho_steakhouse_usdc": ("0xBEEFE94c8aD530842bfE7d8B397938fFc1cb83b2", "morpho"),
        "morpho_gauntlet_usdc_prime": ("0xeE8F4eC5672F09119b96Ab6fB59C27E1b7e44b61", "morpho"),
        "morpho_pangolins_usdc": ("0x1401d1271C47648AC70cBcdfA3776D4A87CE006B", "morpho"),
        "morpho_gauntlet_rwa_usdc": ("0xA8875aaeBc4f830524e35d57F9772FfAcbdD6C45", "morpho"),
    }
    updated = []
    protos = await store.list_protocols()
    for p in protos:
        if p.name in VAULT_ADDRESSES:
            addr, coll = VAULT_ADDRESSES[p.name]
            if p.vault_address != addr or p.collector != coll:
                await store.update_protocol(p.id, vault_address=addr, collector=coll)
                updated.append({"name": p.name, "vault_address": addr})
    return {"updated": updated}


@router.post("/refresh")
async def refresh_all_protocols(
    name_filter: str | None = None,
    store: ConfigStore = Depends(get_config_store),
    storage: Storage = Depends(get_storage),
):
    """Manually trigger DefiLlama refresh for all enabled protocols.

    Optional `name_filter` query param limits refresh to a single protocol name."""
    from stake_watch.collectors.defillama import DefiLlamaCollector
    from stake_watch.models.common import Chain
    from datetime import datetime, timezone

    DEFILLAMA_CHAIN_MAP = {"base": "Base", "ethereum": "Ethereum", "bsc": "BSC", "solana": "Solana"}
    SLUG_MAP = {
        "aave_v3_base": "aave-v3",
        "compound_v3_usdc": "compound-v3",
        "sky_susds": "sky-lending",
        "fluid_usdc": "fluid-lending",
        "jupiter_lend": "jupiter-lend",
        "kamino_usdc": "kamino-lend",
        "morpho_steakhouse_usdc": "morpho-blue",
        "morpho_gauntlet_usdc_prime": "morpho-blue",
        "morpho_pangolins_usdc": "morpho-blue",
        "morpho_gauntlet_rwa_usdc": "morpho-blue",
    }
    POOL_FILTER_MAP = {
        "morpho_steakhouse_usdc": "STEAKUSDC",
        "morpho_gauntlet_usdc_prime": "GTUSDCP",
        "morpho_pangolins_usdc": "PUSDC",
        "morpho_gauntlet_rwa_usdc": "GAUNTLETUSDCRWA",
        "sky_susds": "SUSDS",
    }

    refreshed = []
    failed = []
    protos = await store.list_protocols()

    # Auto-fix missing vault addresses for known Morpho protocols
    KNOWN_VAULTS = {
        "morpho_steakhouse_usdc": "0xBEEFE94c8aD530842bfE7d8B397938fFc1cb83b2",
        "morpho_gauntlet_usdc_prime": "0xeE8F4eC5672F09119b96Ab6fB59C27E1b7e44b61",
        "morpho_pangolins_usdc": "0x1401d1271C47648AC70cBcdfA3776D4A87CE006B",
        "morpho_gauntlet_rwa_usdc": "0xA8875aaeBc4f830524e35d57F9772FfAcbdD6C45",
    }
    # Auto-rename and migrate old morpho_gauntlet_frontier_usdc → morpho_gauntlet_rwa_usdc
    for p in protos:
        if p.name == "morpho_gauntlet_frontier_usdc":
            await store.update_protocol(p.id,
                name="morpho_gauntlet_rwa_usdc",
                vault_address="0xA8875aaeBc4f830524e35d57F9772FfAcbdD6C45",
                collector="morpho",
                primary_risks='["RWA exposure", "broader collateral acceptance for yield"]')
        if p.name == "sky_susds" and p.defillama_slug == "sky":
            await store.update_protocol(p.id, defillama_slug="sky-lending")
    # Auto-fix deprecated Ethereum RPC
    try:
        rpc_list_pre = await store.list_rpc()
        for r in rpc_list_pre:
            if r.chain == "ethereum" and r.primary_url == "https://eth.public-rpc.com":
                await store.upsert_rpc("ethereum", "https://ethereum.publicnode.com", [])
    except Exception:
        pass
    # Backfill protocol_type for legacy rows
    for p in protos:
        if not getattr(p, "protocol_type", None):
            await store.update_protocol(p.id, protocol_type=_classify(p.name))
    for p in protos:
        if p.name in KNOWN_VAULTS and not p.vault_address:
            await store.update_protocol(p.id, vault_address=KNOWN_VAULTS[p.name])
    protos = await store.list_protocols()

    for p in protos:
        if not p.enabled:
            continue
        if name_filter and p.name != name_filter:
            continue

        # Morpho vaults: use Morpho API for accurate per-vault data
        if p.vault_address and p.chain.lower() in ("base", "ethereum"):
            try:
                from stake_watch.collectors.morpho.morpho_api import fetch_vault_data
                from stake_watch.models.protocol import PoolStats, ProtocolStats
                from datetime import datetime, timezone
                vd = await fetch_vault_data(p.vault_address, p.chain)
                if vd:
                    # Persist share price for trend analysis
                    if vd.get("share_price_usd"):
                        try:
                            await storage.save_vault_share_price(p.vault_address, p.name, vd["share_price_usd"])
                        except Exception:
                            pass
                    pool = PoolStats(
                        pool_id=p.vault_address, asset=vd["asset"],
                        supply_apy=vd["apy"], borrow_apy=0,
                        total_supply=Decimal(str(vd["tvl_usd"])),
                        total_borrow=Decimal("0"), utilization=0)
                    stats = ProtocolStats(
                        chain=Chain(p.chain), protocol=p.name,
                        tvl_usd=Decimal(str(vd["tvl_usd"])), pools=[pool],
                        updated_at=datetime.now(timezone.utc))
                    await storage.save_protocol_stats(stats)

                    chain_display = CHAIN_DISPLAY.get(DEFILLAMA_CHAIN_MAP.get(p.chain, ""), p.chain.upper())
                    chains_data = [{
                        "chain": chain_display,
                        "chain_full": DEFILLAMA_CHAIN_MAP.get(p.chain, p.chain),
                        "tvl_usd": vd["tvl_usd"],
                        "apy": vd["apy"],
                        "pools": 1,
                        "by_asset": {vd["asset"]: {
                            "tvl_usd": vd["tvl_usd"], "apy": vd["apy"], "pools": 1,
                            "share_price_usd": vd.get("share_price_usd"),
                        }},
                    }]
                    await store.set_setting(f"protocols.{p.name}.chains", chains_data)

                    refreshed.append({
                        "name": p.name, "tvl_usd": vd["tvl_usd"],
                        "apy": vd["apy"], "asset": vd["asset"],
                        "pools": 1, "chains": 1, "source": "Morpho API",
                    })
                    continue
            except Exception as e:
                failed.append({"name": p.name, "reason": f"Morpho API: {e}"})
                continue

        # Kamino: use official API for accurate per-reserve data
        if p.collector == "kamino" or p.name.startswith("kamino_"):
            try:
                from stake_watch.collectors.kamino.kamino_api import fetch_kamino_stable_reserves
                from stake_watch.models.protocol import PoolStats, ProtocolStats
                from datetime import datetime, timezone
                reserves = await fetch_kamino_stable_reserves()
                if reserves:
                    pools = [PoolStats(
                        pool_id=f"kamino_main_{r['asset']}",
                        asset=r["asset"], supply_apy=r["apy"], borrow_apy=0,
                        total_supply=Decimal(str(r["tvl_usd"])),
                        total_borrow=Decimal("0"), utilization=0,
                    ) for r in reserves]
                    total_tvl = sum(Decimal(str(r["tvl_usd"])) for r in reserves)
                    stats = ProtocolStats(chain=Chain(p.chain), protocol=p.name,
                        tvl_usd=total_tvl, pools=pools,
                        updated_at=datetime.now(timezone.utc))
                    await storage.save_protocol_stats(stats)

                    by_asset = {r["asset"]: {"tvl_usd": r["tvl_usd"], "apy": r["apy"],
                                              "pools": 1, "utilization": r.get("utilization", 0),
                                              "withdrawable_ratio": r.get("withdrawable_ratio", 0),
                                              "available_liquidity_usd": r.get("available_liquidity_usd", 0)}
                                for r in reserves}
                    chains_data = [{
                        "chain": "SOL", "chain_full": "Solana",
                        "tvl_usd": float(total_tvl),
                        "apy": sum(r["apy"] for r in reserves) / len(reserves),
                        "pools": len(reserves), "by_asset": by_asset,
                    }]
                    await store.set_setting(f"protocols.{p.name}.chains", chains_data)

                    primary = next((r for r in reserves if r["asset"] == "USDC"), reserves[0])
                    refreshed.append({
                        "name": p.name, "tvl_usd": float(total_tvl),
                        "apy": primary["apy"], "asset": primary["asset"],
                        "pools": len(reserves), "chains": 1, "source": "Kamino API",
                    })
                    continue
            except Exception as e:
                failed.append({"name": p.name, "reason": f"Kamino API: {type(e).__name__}: {e}"})
                continue

        # Jupiter Lend: use official API for per-token data
        if p.name.startswith("jupiter_"):
            try:
                from stake_watch.collectors.jupiter.jupiter_api import fetch_jupiter_lend_stable_reserves
                from stake_watch.models.protocol import PoolStats, ProtocolStats
                from datetime import datetime, timezone
                reserves = await fetch_jupiter_lend_stable_reserves()
                if reserves:
                    pools = [PoolStats(
                        pool_id=f"jupiter_lend_{r['asset']}",
                        asset=r["asset"], supply_apy=r["apy"], borrow_apy=0,
                        total_supply=Decimal(str(r["tvl_usd"])),
                        total_borrow=Decimal("0"), utilization=0,
                    ) for r in reserves]
                    total_tvl = sum(Decimal(str(r["tvl_usd"])) for r in reserves)
                    stats = ProtocolStats(chain=Chain(p.chain), protocol=p.name,
                        tvl_usd=total_tvl, pools=pools,
                        updated_at=datetime.now(timezone.utc))
                    await storage.save_protocol_stats(stats)

                    by_asset = {r["asset"]: {"tvl_usd": r["tvl_usd"], "apy": r["apy"], "pools": 1,
                                              "withdrawable_ratio": r.get("withdrawable_ratio", 0),
                                              "available_liquidity_usd": r.get("available_liquidity_usd", 0)}
                                for r in reserves}
                    chains_data = [{
                        "chain": "SOL", "chain_full": "Solana",
                        "tvl_usd": float(total_tvl),
                        "apy": sum(r["apy"] for r in reserves) / len(reserves),
                        "pools": len(reserves), "by_asset": by_asset,
                    }]
                    await store.set_setting(f"protocols.{p.name}.chains", chains_data)

                    primary = next((r for r in reserves if r["asset"] == "USDC"), reserves[0])
                    refreshed.append({
                        "name": p.name, "tvl_usd": float(total_tvl),
                        "apy": primary["apy"], "asset": primary["asset"],
                        "pools": len(reserves), "chains": 1, "source": "Jupiter Lend API",
                    })
                    continue
            except Exception as e:
                failed.append({"name": p.name, "reason": f"Jupiter Lend API: {type(e).__name__}: {e}"})
                continue

        # Aave V3: use official GraphQL API
        if p.name.startswith("aave_"):
            try:
                from stake_watch.collectors.aave.aave_api import fetch_aave_v3_stable_data
                from stake_watch.models.protocol import PoolStats, ProtocolStats
                from datetime import datetime, timezone
                chains_data = await fetch_aave_v3_stable_data()
                if chains_data:
                    primary_chain = DEFILLAMA_CHAIN_MAP.get(p.chain, p.chain)
                    primary_short = CHAIN_DISPLAY.get(primary_chain, p.chain.upper())
                    primary_entry = next((c for c in chains_data if c["chain"] == primary_short), chains_data[0])
                    pools = []
                    total_tvl = Decimal("0")
                    for asset, info in primary_entry.get("by_asset", {}).items():
                        pools.append(PoolStats(
                            pool_id=f"aave_v3_{primary_short}_{asset}",
                            asset=asset, supply_apy=info["apy"], borrow_apy=0,
                            total_supply=Decimal(str(info["tvl_usd"])),
                            total_borrow=Decimal("0"), utilization=0))
                        total_tvl += Decimal(str(info["tvl_usd"]))
                    stats = ProtocolStats(chain=Chain(p.chain), protocol=p.name,
                        tvl_usd=total_tvl, pools=pools,
                        updated_at=datetime.now(timezone.utc))
                    await storage.save_protocol_stats(stats)
                    await store.set_setting(f"protocols.{p.name}.chains", chains_data)
                    primary_asset_info = primary_entry["by_asset"].get("USDC") or next(iter(primary_entry["by_asset"].values()), None)
                    refreshed.append({
                        "name": p.name, "tvl_usd": float(total_tvl),
                        "apy": primary_asset_info["apy"] if primary_asset_info else 0,
                        "asset": "USDC" if "USDC" in primary_entry["by_asset"] else "",
                        "pools": len(pools), "chains": len(chains_data),
                        "source": "Aave V3 API",
                    })
                    continue
            except Exception as e:
                failed.append({"name": p.name, "reason": f"Aave V3 API: {type(e).__name__}: {e}"})
                continue

        # Compound V3: use official REST API
        if p.name.startswith("compound_"):
            try:
                from stake_watch.collectors.compound.compound_api import fetch_compound_v3_stable_data
                from stake_watch.models.protocol import PoolStats, ProtocolStats
                from datetime import datetime, timezone
                chains_data = await fetch_compound_v3_stable_data()
                if chains_data:
                    primary_chain = DEFILLAMA_CHAIN_MAP.get(p.chain, p.chain)
                    primary_short = CHAIN_DISPLAY.get(primary_chain, p.chain.upper())
                    primary_entry = next((c for c in chains_data if c["chain"] == primary_short), chains_data[0])
                    pools = []
                    total_tvl = Decimal("0")
                    for asset, info in primary_entry.get("by_asset", {}).items():
                        pools.append(PoolStats(
                            pool_id=f"compound_v3_{primary_short}_{asset}",
                            asset=asset, supply_apy=info["apy"], borrow_apy=0,
                            total_supply=Decimal(str(info["tvl_usd"])),
                            total_borrow=Decimal("0"), utilization=0))
                        total_tvl += Decimal(str(info["tvl_usd"]))
                    stats = ProtocolStats(chain=Chain(p.chain), protocol=p.name,
                        tvl_usd=total_tvl, pools=pools,
                        updated_at=datetime.now(timezone.utc))
                    await storage.save_protocol_stats(stats)
                    await store.set_setting(f"protocols.{p.name}.chains", chains_data)
                    primary_asset_info = primary_entry["by_asset"].get("USDC") or next(iter(primary_entry["by_asset"].values()), None)
                    refreshed.append({
                        "name": p.name, "tvl_usd": float(total_tvl),
                        "apy": primary_asset_info["apy"] if primary_asset_info else 0,
                        "asset": "USDC" if "USDC" in primary_entry["by_asset"] else "",
                        "pools": len(pools), "chains": len(chains_data),
                        "source": "Compound V3 API",
                    })
                    continue
            except Exception as e:
                failed.append({"name": p.name, "reason": f"Compound V3 API: {type(e).__name__}: {e}"})
                continue

        # Sky sUSDS: read SSR on-chain
        if p.name == "sky_susds":
            try:
                from stake_watch.collectors.sky.sky_api import fetch_sky_susds_data
                from stake_watch.models.protocol import PoolStats, ProtocolStats
                from datetime import datetime, timezone
                rpc_list = await store.list_rpc()
                eth_rpc = next((r.primary_url for r in rpc_list if r.chain == "ethereum"), None)
                if not eth_rpc:
                    raise RuntimeError("no ethereum RPC configured")
                sky = await fetch_sky_susds_data(eth_rpc)
                if sky:
                    pool = PoolStats(pool_id="sky_susds", asset=sky["asset"],
                        supply_apy=sky["apy"], borrow_apy=0,
                        total_supply=Decimal(str(sky["tvl_usd"])),
                        total_borrow=Decimal("0"), utilization=0)
                    stats = ProtocolStats(chain=Chain(p.chain), protocol=p.name,
                        tvl_usd=Decimal(str(sky["tvl_usd"])), pools=[pool],
                        updated_at=datetime.now(timezone.utc))
                    await storage.save_protocol_stats(stats)

                    chains_data = [{
                        "chain": "ETH", "chain_full": "Ethereum",
                        "tvl_usd": sky["tvl_usd"], "apy": sky["apy"], "pools": 1,
                        "by_asset": {sky["asset"]: {"apy": sky["apy"], "tvl_usd": sky["tvl_usd"], "pools": 1}},
                    }]
                    await store.set_setting(f"protocols.{p.name}.chains", chains_data)
                    refreshed.append({
                        "name": p.name, "tvl_usd": sky["tvl_usd"],
                        "apy": sky["apy"], "asset": sky["asset"],
                        "pools": 1, "chains": 1, "source": "Sky on-chain (SSR)",
                    })
                    continue
            except Exception as e:
                failed.append({"name": p.name, "reason": f"Sky on-chain: {type(e).__name__}: {e}"})
                continue

        slug = p.defillama_slug or SLUG_MAP.get(p.name)
        if not slug:
            failed.append({"name": p.name, "reason": "no defillama_slug"})
            continue
        pool_filter = getattr(p, "pool_filter", None) or POOL_FILTER_MAP.get(p.name)
        try:
            collector = DefiLlamaCollector(
                chain=Chain(p.chain), protocol=p.name,
                defillama_slug=slug,
                chain_filter=DEFILLAMA_CHAIN_MAP.get(p.chain, p.chain),
                pool_filter=pool_filter,
            )
            stats = await collector.collect_protocol_stats()
            if not stats.pools:
                failed.append({"name": p.name, "reason": f"DefiLlama 无匹配池 (slug={slug}, chain={DEFILLAMA_CHAIN_MAP.get(p.chain, p.chain)}, filter={pool_filter or '-'})"})
                continue
            await storage.save_protocol_stats(stats)
            usdc_pool = next((pp for pp in stats.pools if "USDC" in pp.asset.upper() or "USD" in pp.asset.upper()), stats.pools[0] if stats.pools else None)

            chains = await _fetch_multi_chain_data(slug, pool_filter)
            if chains:
                await store.set_setting(f"protocols.{p.name}.chains", chains)

            refreshed.append({
                "name": p.name,
                "tvl_usd": float(stats.tvl_usd),
                "apy": usdc_pool.supply_apy if usdc_pool else 0,
                "asset": usdc_pool.asset if usdc_pool else "",
                "pools": len(stats.pools),
                "chains": len(chains),
            })
        except Exception as e:
            failed.append({"name": p.name, "reason": f"{type(e).__name__}: {e}" if str(e) else type(e).__name__})

    # Write TVL snapshots for trend analysis
    try:
        for r in refreshed:
            proto_name = r["name"]
            chains_data = await store.get_setting(f"protocols.{proto_name}.chains") or []
            for entry in chains_data:
                chain_full = (entry.get("chain_full") or entry.get("chain") or "").lower()
                for asset, info in (entry.get("by_asset") or {}).items():
                    tvl = float(info.get("tvl_usd") or 0)
                    apy = float(info.get("apy") or 0)
                    if tvl > 0:
                        await storage.save_tvl_snapshot(proto_name, chain_full, asset.upper(), tvl, apy)
    except Exception as e:
        logger = __import__("logging").getLogger(__name__)
        logger.warning(f"TVL snapshot write failed: {e}")

    return {"refreshed": refreshed, "failed": failed,
            "updated_at": datetime.now(timezone.utc).isoformat()}


@router.get("/report-config")
async def get_protocols_report_config(store: ConfigStore = Depends(get_config_store)):
    interval = await store.get_setting("protocols.report_interval") or 14400
    enabled = await store.get_setting("protocols.report_enabled")
    if enabled is None:
        enabled = True
    return {"interval": interval, "enabled": enabled}


class ProtocolsReportConfigUpdate(BaseModel):
    interval: int | None = None
    enabled: bool | None = None


@router.put("/report-config")
async def update_protocols_report_config(data: ProtocolsReportConfigUpdate,
                                          store: ConfigStore = Depends(get_config_store)):
    if data.interval is not None:
        await store.set_setting("protocols.report_interval", data.interval)
    if data.enabled is not None:
        await store.set_setting("protocols.report_enabled", data.enabled)
    return await get_protocols_report_config(store)


@router.post("/report/send")
async def send_protocols_report_now(storage: Storage = Depends(get_storage)):
    from stake_watch.alerts.protocols_report import send_protocols_report
    try:
        await send_protocols_report(storage)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
