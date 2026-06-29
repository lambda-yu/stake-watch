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
        # Track consecutive failures per collector → fire one alert at threshold,
        # then reset on success. Avoids spamming on flaky upstreams.
        self._consecutive_failures: dict[str, int] = {}
        self.failure_alert_threshold = 3  # 3 consecutive failures before alerting

    async def _on_collector_failure(self, collector: BaseCollector, error: str):
        proto = collector.protocol
        self._consecutive_failures[proto] = self._consecutive_failures.get(proto, 0) + 1
        if self._consecutive_failures[proto] != self.failure_alert_threshold:
            return  # only alert exactly on threshold crossing
        try:
            from datetime import datetime, timezone
            from stake_watch.models.alert import Alert, RuleType, Severity
            chain_val = getattr(collector, "chain", None)
            chain_str = chain_val.value if hasattr(chain_val, "value") else str(chain_val or "")
            alert = Alert(
                rule_type=RuleType.COLLECTOR_FAILURE,
                severity=Severity.WARNING,
                protocol=proto, chain=chain_str,
                title=f"{proto} 采集连续失败 {self.failure_alert_threshold} 次",
                message=str(error)[:500],
                details={"consecutive_failures": self._consecutive_failures[proto],
                         "error": str(error)[:500]},
                created_at=datetime.now(timezone.utc),
            )
            await self.storage.save_alert(alert)
            # Best-effort Telegram push
            try:
                from stake_watch.storage.config_store import ConfigStore
                from stake_watch.alerts.telegram import TelegramNotifier
                cs = ConfigStore(self.storage._session_factory)
                bt = await cs.get_setting("telegram.bot_token")
                cid = await cs.get_setting("telegram.chat_id")
                if bt and cid:
                    await TelegramNotifier(bot_token=bt, chat_id=cid).send(alert)
            except Exception as push_err:
                logger.warning(f"collector_failure telegram push failed: {push_err}")
        except Exception as e:
            logger.error(f"failed to record collector_failure alert: {e}")

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
                await self._on_collector_failure(collector, "; ".join(result.errors)[:500])
            else:
                # success → reset counter so future failures can re-alert
                self._consecutive_failures.pop(collector.protocol, None)
            return result
        except Exception as e:
            logger.error(f"{collector.protocol}: unhandled error: {e}")
            await self._on_collector_failure(collector, str(e))
            return CollectResult(errors=[str(e)])

    async def run_collection_cycle(self) -> list[CollectResult]:
        results = []
        for collector in self.collectors:
            for wallet in self.wallets:
                result = await self._run_single(collector, wallet)
                results.append(result)
        return results


from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

class ScheduledRunner:
    def __init__(self, collection_runner: CollectionRunner, position_interval: int = 300,
                 stats_interval: int = 900, stablecoin_report_interval: int = 3600,
                 dex_liquidity_interval: int = 300, reserves_fetch_interval: int = 21600,
                 protocols_report_interval: int = 14400,
                 snapshots_interval: int = 14400,
                 risk_monitor_interval: int = 3600,
                 screenshot_daily: dict | None = None,
                 storage: Storage | None = None):
        self.collection_runner = collection_runner
        self.position_interval = position_interval
        self.stats_interval = stats_interval
        self.stablecoin_report_interval = stablecoin_report_interval
        self.dex_liquidity_interval = dex_liquidity_interval
        self.reserves_fetch_interval = reserves_fetch_interval
        self.protocols_report_interval = protocols_report_interval
        self.snapshots_interval = snapshots_interval
        self.risk_monitor_interval = risk_monitor_interval
        self.screenshot_daily = screenshot_daily or {}
        self.storage = storage
        self._scheduler = AsyncIOScheduler()

    async def trigger_now(self):
        await self.collection_runner.run_collection_cycle()

    async def _send_stablecoin_report(self):
        if not self.storage:
            return
        from stake_watch.alerts.stablecoin_report import send_stablecoin_report
        await send_stablecoin_report(self.storage)

    async def _send_protocols_report(self):
        if not self.storage:
            return
        from stake_watch.alerts.protocols_report import send_protocols_report
        await send_protocols_report(self.storage)

    async def _write_snapshots(self):
        if not self.storage:
            return
        from stake_watch.storage.config_store import ConfigStore
        from stake_watch.storage.snapshots import (
            write_tvl_snapshots_from_settings,
            write_vault_share_price_snapshots,
        )
        store = ConfigStore(self.storage._session_factory)
        try:
            tvl_n = await write_tvl_snapshots_from_settings(store, self.storage)
            sp_n = await write_vault_share_price_snapshots(store, self.storage)
            logger.info(f"Snapshots written: tvl={tvl_n} share_price={sp_n}")
        except Exception as e:
            logger.error(f"Snapshot job failed: {e}")

    async def _run_risk_monitor(self):
        if not self.storage:
            return
        from stake_watch.risk.protocol_risk_monitor import run_risk_monitor_with_telegram
        try:
            n = await run_risk_monitor_with_telegram(self.storage)
            if n:
                logger.info(f"Risk monitor emitted {n} alert(s)")
        except Exception as e:
            logger.error(f"Risk monitor failed: {e}")

    async def _send_comparison_screenshot(self):
        if not self.storage:
            return
        from stake_watch.alerts.comparison_screenshot import send_comparison_screenshot
        try:
            r = await send_comparison_screenshot(self.storage)
            if r.get("success"):
                logger.info(f"Comparison screenshot pushed ({r.get('bytes', 0)} bytes)")
            else:
                logger.warning(f"Scheduled comparison screenshot failed: {r.get('error')}")
        except Exception as e:
            logger.error(f"Comparison screenshot job failed: {e}")

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
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                await config_store.set_setting("reserves.usdt.total_reserves", float(tether["total_assets"]))
                await config_store.set_setting("reserves.usdt.coverage_ratio", tether["coverage_ratio"])
                await config_store.set_setting("reserves.usdt.report_date", today)
                await config_store.set_setting("reserves.usdt.last_fetched", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))

            circle = await fetch_circle_supply()
            if circle:
                supply = float(circle["total_supply"])
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                await config_store.set_setting("reserves.usdc.total_reserves", supply)
                await config_store.set_setting("reserves.usdc.total_supply_live", supply)
                await config_store.set_setting("reserves.usdc.report_date", today)
                await config_store.set_setting("reserves.usdc.last_fetched", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))

            # USD0/USD1 via DefiLlama supply
            try:
                from stake_watch.collectors.stablecoin.supply import StablecoinSupplyCollector
                supply_collector = StablecoinSupplyCollector()
                supplies = await supply_collector.collect_supply()
                for s in supplies:
                    if s.token in ("USD0", "USD1"):
                        tl = s.token.lower()
                        sv = float(s.total_circulating)
                        await config_store.set_setting(f"reserves.{tl}.total_reserves", sv)
                        await config_store.set_setting(f"reserves.{tl}.total_supply_live", sv)
                        await config_store.set_setting(f"reserves.{tl}.last_fetched", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))
                        await config_store.set_setting(f"reserves.{tl}.report_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            except Exception:
                pass

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

        if self.protocols_report_interval > 0 and self.storage:
            self._scheduler.add_job(self._send_protocols_report,
                trigger=IntervalTrigger(seconds=self.protocols_report_interval),
                id="protocols_report", name="Protocols report", replace_existing=True)
            logger.info(f"Protocols report every {self.protocols_report_interval}s")

        if self.snapshots_interval > 0 and self.storage:
            self._scheduler.add_job(self._write_snapshots,
                trigger=IntervalTrigger(seconds=self.snapshots_interval),
                id="snapshots", name="TVL + share-price snapshots",
                replace_existing=True)
            logger.info(f"Snapshots every {self.snapshots_interval}s")

        if self.risk_monitor_interval > 0 and self.storage:
            self._scheduler.add_job(self._run_risk_monitor,
                trigger=IntervalTrigger(seconds=self.risk_monitor_interval),
                id="risk_monitor", name="Risk monitor + alerts",
                replace_existing=True)
            logger.info(f"Risk monitor every {self.risk_monitor_interval}s")

        sd = self.screenshot_daily
        if sd.get("enabled") and self.storage:
            self.apply_screenshot_daily_config(
                enabled=True,
                hour=int(sd.get("hour", 9)),
                minute=int(sd.get("minute", 0)),
                tz_offset=int(sd.get("tz_offset", 8)),
            )

        self._scheduler.start()
        logger.info(f"Scheduler started: positions every {self.position_interval}s")

    def apply_screenshot_daily_config(self, *, enabled: bool, hour: int,
                                        minute: int, tz_offset: int) -> str:
        """Hot-reload the daily screenshot cron job. Returns a status string.

        Safe to call before or after _scheduler.start(). When `enabled` is False,
        any existing screenshot_daily job is removed.
        """
        self.screenshot_daily = {"enabled": enabled, "hour": hour,
                                  "minute": minute, "tz_offset": tz_offset}
        if not self.storage:
            return "no storage; skipped"
        existing = self._scheduler.get_job("screenshot_daily")
        if not enabled:
            if existing:
                self._scheduler.remove_job("screenshot_daily")
                logger.info("Daily comparison screenshot job removed")
                return "removed"
            return "disabled (no prior job)"
        from datetime import timedelta, timezone as _tz
        tz = _tz(timedelta(hours=tz_offset))
        self._scheduler.add_job(
            self._send_comparison_screenshot,
            trigger=CronTrigger(hour=hour, minute=minute, timezone=tz),
            id="screenshot_daily", name="Daily comparison screenshot",
            replace_existing=True,
        )
        logger.info(f"Comparison screenshot daily at {hour:02d}:{minute:02d} UTC{tz_offset:+d}")
        return "scheduled"

    def stop(self):
        self._scheduler.shutdown(wait=False)
