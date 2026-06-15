from __future__ import annotations
import asyncio
import logging
from pathlib import Path
import uvicorn
from stake_watch.api.app import create_app
from stake_watch.collectors.base import BaseCollector
from stake_watch.collectors.registry import build_collector
from stake_watch.config import load_protocols, load_settings
from stake_watch.scheduler.runner import CollectionRunner, ScheduledRunner
from stake_watch.storage.db import Storage

logger = logging.getLogger(__name__)

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
    rpc_urls = {chain: ep.primary for chain, ep in settings.rpc.items()}
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

    app = create_app(storage)

    scheduled = ScheduledRunner(
        collection_runner=runner,
        position_interval=settings.intervals.positions,
        stats_interval=settings.intervals.protocol_stats,
    )

    logger.info(
        f"Stake Watch started with {len(runner.collectors)} collectors, "
        f"{len(runner.wallets)} wallets"
    )

    await scheduled.trigger_now()
    scheduled.start()

    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    try:
        await server.serve()
    finally:
        scheduled.stop()
        await storage.close()

if __name__ == "__main__":
    asyncio.run(main())
