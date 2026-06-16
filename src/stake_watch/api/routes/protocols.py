import json
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

def _to_dict(p):
    return {"id": p.id, "name": p.name, "chain": p.chain, "collector": p.collector,
        "enabled": p.enabled, "safety_rank": p.safety_rank, "safety_score": p.safety_score,
        "reference_apy": p.reference_apy, "primary_risks": json.loads(p.primary_risks) if p.primary_risks else [],
        "vault_address": p.vault_address, "defillama_slug": p.defillama_slug,
        "pool_filter": getattr(p, "pool_filter", None)}


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

@router.delete("/{protocol_id}", status_code=204)
async def delete_protocol(protocol_id: int, store: ConfigStore = Depends(get_config_store)):
    await store.delete_protocol(protocol_id)
    return Response(status_code=204)


@router.post("/refresh")
async def refresh_all_protocols(
    store: ConfigStore = Depends(get_config_store),
    storage: Storage = Depends(get_storage),
):
    """Manually trigger DefiLlama refresh for all enabled protocols.

    Uses pool_filter when set (e.g. vault symbol for Morpho)."""
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
        "morpho_gauntlet_frontier_usdc": "morpho-blue",
    }
    POOL_FILTER_MAP = {
        "morpho_steakhouse_usdc": "STEAKUSDC",
        "morpho_gauntlet_usdc_prime": "GTUSDCP",
        "morpho_pangolins_usdc": "PUSDC",
        "morpho_gauntlet_frontier_usdc": "GTUSDC",
        "sky_susds": "SUSDS",
    }

    refreshed = []
    failed = []
    protos = await store.list_protocols()

    for p in protos:
        if not p.enabled:
            continue

        # Morpho vaults: use Morpho API for accurate per-vault data
        if p.vault_address and p.chain.lower() in ("base", "ethereum"):
            try:
                from stake_watch.collectors.morpho.morpho_api import fetch_vault_data
                from stake_watch.models.protocol import PoolStats, ProtocolStats
                from datetime import datetime, timezone
                vd = await fetch_vault_data(p.vault_address, p.chain)
                if vd:
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
                        "by_asset": {vd["asset"]: {"tvl_usd": vd["tvl_usd"], "apy": vd["apy"], "pools": 1}},
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
            failed.append({"name": p.name, "reason": str(e)})

    return {"refreshed": refreshed, "failed": failed,
            "updated_at": datetime.now(timezone.utc).isoformat()}
