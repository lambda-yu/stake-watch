from __future__ import annotations
import asyncio
import logging
from pathlib import Path
from stake_watch.collectors.base import BaseCollector
from stake_watch.collectors.defillama import DefiLlamaCollector
from stake_watch.config import AppSettings, ProtocolEntry, load_protocols, load_settings
from stake_watch.models.common import Chain
from stake_watch.scheduler.runner import CollectionRunner
from stake_watch.storage.db import Storage

logger = logging.getLogger(__name__)

DEFILLAMA_CHAIN_MAP = {"base": "Base", "ethereum": "Ethereum", "bsc": "BSC", "solana": "Solana"}
DEFILLAMA_SLUG_MAP = {
    "aave_v3_base": "aave-v3", "morpho_steakhouse_usdc": "morpho-blue",
    "morpho_gauntlet_usdc_prime": "morpho-blue", "morpho_pangolins_usdc": "morpho-blue",
    "morpho_gauntlet_frontier_usdc": "morpho-blue", "jupiter_lend": "jupiter-lend",
    "kamino_usdc": "kamino-lend", "compound_v3_usdc": "compound-v3",
    "fluid_usdc": "fluid-lending", "sky_susds": "sky", "venus_usdc": "venus-core-pool",
}

def _build_collector(entry: ProtocolEntry) -> BaseCollector | None:
    chain = Chain(entry.chain)
    slug = entry.defillama_slug or DEFILLAMA_SLUG_MAP.get(entry.name)
    if slug:
        return DefiLlamaCollector(chain=chain, protocol=entry.name, defillama_slug=slug,
            chain_filter=DEFILLAMA_CHAIN_MAP.get(entry.chain, entry.chain))
    logger.warning(f"No collector mapping for {entry.name}, skipping")
    return None

async def build_app(settings_path=None, protocols_path=None, local_settings_path=None):
    settings_path = settings_path or Path("config/settings.yaml")
    protocols_path = protocols_path or Path("config/protocols.yaml")
    local_settings_path = local_settings_path or Path("config/settings.local.yaml")
    settings = load_settings(settings_path, local_path=local_settings_path)
    protocols = load_protocols(protocols_path) if protocols_path.exists() else []
    db_url = settings.database.url
    if not db_url.startswith("sqlite+aiosqlite"):
        db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    storage = Storage(db_url)
    await storage.initialize()
    collectors = []
    for entry in protocols:
        if not entry.enabled:
            continue
        collector = _build_collector(entry)
        if collector:
            collectors.append(collector)
    wallets = [w.address for w in settings.wallets]
    runner = CollectionRunner(collectors=collectors, storage=storage, wallets=wallets or [""])
    return runner, storage, settings

async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    runner, storage, settings = await build_app()
    logger.info(f"Stake Watch started with {len(runner.collectors)} collectors, {len(runner.wallets)} wallets")
    try:
        results = await runner.run_collection_cycle()
        for r in results:
            if r.protocol_stats:
                logger.info(f"  {r.protocol_stats.protocol}: TVL=${r.protocol_stats.tvl_usd:,.0f}, {len(r.protocol_stats.pools)} pools")
            for err in r.errors:
                logger.warning(f"  Error: {err}")
    finally:
        await storage.close()

if __name__ == "__main__":
    asyncio.run(main())
