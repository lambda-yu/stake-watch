from __future__ import annotations
import logging
from stake_watch.collectors.base import BaseCollector
from stake_watch.collectors.defillama import DefiLlamaCollector
from stake_watch.config import ProtocolEntry
from stake_watch.models.common import Chain

logger = logging.getLogger(__name__)

DEFILLAMA_CHAIN_MAP = {"base": "Base", "ethereum": "Ethereum", "bsc": "BSC", "solana": "Solana"}

def build_collector(entry: ProtocolEntry, rpc_urls: dict[str, str]) -> BaseCollector | None:
    chain = Chain(entry.chain)
    rpc_url = rpc_urls.get(entry.chain, "")
    ct = entry.collector

    if ct == "aave_v3":
        from stake_watch.collectors.aave.collector import AaveV3Collector
        from stake_watch.collectors.aave.abi import AAVE_V3_POOL_BASE
        return AaveV3Collector(chain=chain, protocol=entry.name, pool_address=AAVE_V3_POOL_BASE, rpc_url=rpc_url)

    if ct == "compound_v3":
        from stake_watch.collectors.compound.collector import CompoundV3Collector
        from stake_watch.collectors.compound.abi import COMET_USDC_BASE
        return CompoundV3Collector(chain=chain, protocol=entry.name, comet_address=COMET_USDC_BASE, rpc_url=rpc_url)

    if ct == "sky_susds":
        from stake_watch.collectors.sky.collector import SkySusdsCollector
        from stake_watch.collectors.sky.abi import SUSDS_ADDRESS
        return SkySusdsCollector(chain=chain, protocol=entry.name, susds_address=SUSDS_ADDRESS, rpc_url=rpc_url)

    if ct == "morpho":
        from stake_watch.collectors.morpho.collector import MorphoCollector
        from stake_watch.collectors.morpho.abi import MORPHO_BLUE_BASE
        if not entry.vault_address:
            logger.warning(f"{entry.name}: morpho collector requires vault_address")
            return None
        return MorphoCollector(chain=chain, protocol=entry.name,
            vault_address=entry.vault_address, morpho_address=MORPHO_BLUE_BASE, rpc_url=rpc_url)

    if ct == "kamino":
        from stake_watch.collectors.kamino.collector import KaminoCollector
        return KaminoCollector(chain=chain, protocol=entry.name, rpc_url=rpc_url)

    if ct == "defillama":
        slug = entry.defillama_slug
        if not slug:
            logger.warning(f"{entry.name}: defillama requires defillama_slug")
            return None
        return DefiLlamaCollector(chain=chain, protocol=entry.name, defillama_slug=slug,
            chain_filter=DEFILLAMA_CHAIN_MAP.get(entry.chain, entry.chain),
            pool_filter=entry.pool_filter)

    logger.warning(f"Unknown collector type '{ct}' for {entry.name}")
    return None
