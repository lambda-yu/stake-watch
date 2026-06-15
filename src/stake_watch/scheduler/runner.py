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


from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

class ScheduledRunner:
    def __init__(self, collection_runner: CollectionRunner, position_interval: int = 300, stats_interval: int = 900):
        self.collection_runner = collection_runner
        self.position_interval = position_interval
        self.stats_interval = stats_interval
        self._scheduler = AsyncIOScheduler()

    async def trigger_now(self):
        await self.collection_runner.run_collection_cycle()

    def start(self):
        self._scheduler.add_job(self.collection_runner.run_collection_cycle,
            trigger=IntervalTrigger(seconds=self.position_interval),
            id="positions", name="Collect positions", replace_existing=True)
        self._scheduler.start()
        logger.info(f"Scheduler started: positions every {self.position_interval}s")

    def stop(self):
        self._scheduler.shutdown(wait=False)
