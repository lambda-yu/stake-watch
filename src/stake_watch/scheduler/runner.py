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
        results = []
        for collector in self.collectors:
            for wallet in self.wallets:
                result = await self._run_single(collector, wallet)
                results.append(result)
        return results


from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

class ScheduledRunner:
    def __init__(self, collection_runner: CollectionRunner, position_interval: int = 300,
                 stats_interval: int = 900, stablecoin_report_interval: int = 3600,
                 dex_liquidity_interval: int = 300, reserves_fetch_interval: int = 21600,
                 storage: Storage | None = None):
        self.collection_runner = collection_runner
        self.position_interval = position_interval
        self.stats_interval = stats_interval
        self.stablecoin_report_interval = stablecoin_report_interval
        self.dex_liquidity_interval = dex_liquidity_interval
        self.reserves_fetch_interval = reserves_fetch_interval
        self.storage = storage
        self._scheduler = AsyncIOScheduler()

    async def trigger_now(self):
        await self.collection_runner.run_collection_cycle()

    async def _send_stablecoin_report(self):
        if not self.storage:
            return
        from stake_watch.alerts.stablecoin_report import send_stablecoin_report
        await send_stablecoin_report(self.storage)

    async def _refresh_dex_liquidity(self):
        try:
            from stake_watch.collectors.stablecoin.dex_liquidity import DexLiquidityCollector
            collector = DexLiquidityCollector()
            pools = await collector.collect_pools()
            logger.info(f"DEX liquidity refreshed: {len(pools)} pools")
        except Exception as e:
            logger.error(f"DEX liquidity refresh failed: {e}")

    async def _fetch_reserves(self):
        if not self.storage:
            return
        try:
            from stake_watch.collectors.stablecoin.reserves_fetcher import fetch_tether_reserves, fetch_circle_supply
            from stake_watch.storage.config_store import ConfigStore
            from datetime import datetime, timezone
            config_store = ConfigStore(self.storage._session_factory)

            tether = await fetch_tether_reserves()
            if tether:
                await config_store.set_setting("reserves.usdt.total_reserves", float(tether["total_assets"]))
                await config_store.set_setting("reserves.usdt.coverage_ratio", tether["coverage_ratio"])
                await config_store.set_setting("reserves.usdt.last_fetched", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))

            circle = await fetch_circle_supply()
            if circle:
                supply = float(circle["total_supply"])
                await config_store.set_setting("reserves.usdc.total_reserves", supply)
                await config_store.set_setting("reserves.usdc.total_supply_live", supply)
                await config_store.set_setting("reserves.usdc.last_fetched", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))

            logger.info(f"Reserves fetched: USDT={'OK' if tether else 'FAIL'} USDC={'OK' if circle else 'FAIL'}")
        except Exception as e:
            logger.error(f"Reserves fetch failed: {e}")

    def start(self):
        self._scheduler.add_job(self.collection_runner.run_collection_cycle,
            trigger=IntervalTrigger(seconds=self.position_interval),
            id="positions", name="Collect positions", replace_existing=True)

        if self.stablecoin_report_interval > 0 and self.storage:
            self._scheduler.add_job(self._send_stablecoin_report,
                trigger=IntervalTrigger(seconds=self.stablecoin_report_interval),
                id="stablecoin_report", name="Stablecoin report", replace_existing=True)
            logger.info(f"Stablecoin report every {self.stablecoin_report_interval}s")

        if self.dex_liquidity_interval > 0:
            self._scheduler.add_job(self._refresh_dex_liquidity,
                trigger=IntervalTrigger(seconds=self.dex_liquidity_interval),
                id="dex_liquidity", name="DEX liquidity", replace_existing=True)
            logger.info(f"DEX liquidity every {self.dex_liquidity_interval}s")

        if self.reserves_fetch_interval > 0 and self.storage:
            self._scheduler.add_job(self._fetch_reserves,
                trigger=IntervalTrigger(seconds=self.reserves_fetch_interval),
                id="reserves_fetch", name="Reserves fetch", replace_existing=True)
            logger.info(f"Reserves fetch every {self.reserves_fetch_interval}s")

        self._scheduler.start()
        logger.info(f"Scheduler started: positions every {self.position_interval}s")

    def stop(self):
        self._scheduler.shutdown(wait=False)
