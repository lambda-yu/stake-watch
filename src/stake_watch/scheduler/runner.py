from __future__ import annotations
import asyncio
import logging
from stake_watch.collectors.base import BaseCollector, CollectResult
from stake_watch.storage.db import Storage

logger = logging.getLogger(__name__)

class CollectionRunner:
    def __init__(self, collectors: list[BaseCollector], storage: Storage, wallets: list[str]):
        self.collectors = collectors
        self.storage = storage
        self.wallets = wallets

    async def _run_single(self, collector: BaseCollector, wallet: str) -> CollectResult:
        try:
            result = await collector.collect(wallet)
            if result.positions:
                await self.storage.save_positions(result.positions)
            if result.protocol_stats:
                await self.storage.save_protocol_stats(result.protocol_stats)
            if result.errors:
                for err in result.errors:
                    logger.warning(err)
            return result
        except Exception as e:
            logger.error(f"{collector.protocol}: unhandled error: {e}")
            return CollectResult(errors=[str(e)])

    async def run_collection_cycle(self) -> list[CollectResult]:
        tasks = []
        for collector in self.collectors:
            for wallet in self.wallets:
                tasks.append(self._run_single(collector, wallet))
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return list(results)
