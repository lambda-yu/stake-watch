from __future__ import annotations
import asyncio
import logging
import os
from stake_watch.collectors.base import BaseCollector
from stake_watch.collectors.registry import build_collector
from stake_watch.config import AppSettings, ProtocolEntry
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage
from stake_watch.scheduler.runner import CollectionRunner, ScheduledRunner

logger = logging.getLogger(__name__)

async def build_app(db_url: str | None = None, seed_path: str = "config/seed.yaml"):
    db_url = db_url or os.environ.get("DATABASE_URL", "sqlite:///stake_watch.db")
    if not db_url.startswith("sqlite+aiosqlite"):
        db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)

    storage = Storage(db_url)
    await storage.initialize()

    config_store = ConfigStore(storage._session_factory)
    imported = await config_store.import_seed_if_empty(seed_path)
    if imported:
        logger.info("Imported seed data into DB")

    settings = await config_store.load_app_settings()
    protocols = await config_store.list_protocol_entries()

    rpc_list = await config_store.list_rpc()
    rpc_urls = {r.chain: r.primary_url for r in rpc_list}

    collectors: list[BaseCollector] = []
    for entry in protocols:
        if not entry.enabled:
            continue
        collector = build_collector(entry, rpc_urls=rpc_urls)
        if collector:
            collectors.append(collector)

    wallets = [w.address for w in settings.wallets]
    runner = CollectionRunner(collectors=collectors, storage=storage, wallets=wallets or [""])
    return runner, storage, settings


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    runner, storage, settings = await build_app()

    from stake_watch.api.app import create_app
    app = create_app(storage)

    from stake_watch.storage.config_store import ConfigStore
    config_store = ConfigStore(storage._session_factory)
    report_interval = await config_store.get_setting("stablecoin.report_interval") or 3600
    dex_interval = await config_store.get_setting("stablecoin.dex_liquidity_interval") or 300
    reserves_interval = await config_store.get_setting("stablecoin.reserves_fetch_interval") or 21600
    protocols_report_interval = await config_store.get_setting("protocols.report_interval") or 14400
    protocols_report_enabled = await config_store.get_setting("protocols.report_enabled")
    if protocols_report_enabled is False:
        protocols_report_interval = 0

    scheduled = ScheduledRunner(
        collection_runner=runner,
        position_interval=settings.intervals.positions,
        stats_interval=settings.intervals.protocol_stats,
        stablecoin_report_interval=report_interval,
        dex_liquidity_interval=dex_interval,
        reserves_fetch_interval=reserves_interval,
        protocols_report_interval=protocols_report_interval,
        storage=storage,
    )

    logger.info(
        f"Stake Watch started with {len(runner.collectors)} collectors, "
        f"{len(runner.wallets)} wallets"
    )

    scheduled.start()

    import uvicorn
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)

    async def initial_collection():
        await asyncio.sleep(1)
        logger.info("Running initial collection...")
        await scheduled.trigger_now()

    asyncio.create_task(initial_collection())

    try:
        await server.serve()
    finally:
        scheduled.stop()
        await storage.close()


if __name__ == "__main__":
    asyncio.run(main())
