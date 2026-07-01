"""Tests for the standalone auto-refresh scheduler + config endpoint."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from stake_watch.api import deps
from stake_watch.api.app import create_app
from stake_watch.scheduler.runner import CollectionRunner, ScheduledRunner
from stake_watch.storage.db import Storage


@pytest.fixture
async def env(tmp_path):
    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await s.initialize()
    runner = CollectionRunner(collectors=[], storage=s, wallets=[""])
    sr = ScheduledRunner(
        collection_runner=runner, position_interval=0,
        stablecoin_report_interval=0, dex_liquidity_interval=0,
        reserves_fetch_interval=0, protocols_report_interval=0,
        protocols_refresh_interval=0, snapshots_interval=0,
        risk_monitor_interval=0, screenshot_daily={"enabled": False},
        storage=s,
    )
    sr.start()
    deps.init_scheduler(sr)
    app = create_app(s)
    async with AsyncClient(transport=ASGITransport(app=app),
                             base_url="http://test") as c:
        yield c, s, sr
    sr.stop()
    await s.close()
    deps.init_scheduler(None)


@pytest.mark.asyncio
async def test_default_refresh_config(env):
    c, _, _ = env
    body = (await c.get("/api/protocols/refresh-config")).json()
    assert body == {"interval": 3600, "enabled": True}


@pytest.mark.asyncio
async def test_put_persists_and_hot_reloads(env):
    c, _, sr = env
    r = await c.put("/api/protocols/refresh-config",
                     json={"interval": 1800, "enabled": True})
    body = r.json()
    assert body["interval"] == 1800
    assert body["enabled"] is True
    assert body["hot_reload"] == "scheduled"
    job = sr._scheduler.get_job("protocols_refresh")
    assert job is not None


@pytest.mark.asyncio
async def test_disable_removes_job(env):
    c, _, sr = env
    await c.put("/api/protocols/refresh-config", json={"enabled": True})
    assert sr._scheduler.get_job("protocols_refresh") is not None
    r = await c.put("/api/protocols/refresh-config", json={"enabled": False})
    assert r.json()["hot_reload"] == "removed"
    assert sr._scheduler.get_job("protocols_refresh") is None


@pytest.mark.asyncio
async def test_interval_floor_60s(env):
    c, _, _ = env
    r = await c.put("/api/protocols/refresh-config", json={"interval": 10})
    assert r.json()["interval"] == 60  # clamped


@pytest.mark.asyncio
async def test_apply_refresh_config_disable_via_zero_interval():
    from unittest.mock import MagicMock
    runner = CollectionRunner(collectors=[], storage=None, wallets=[""])
    sr = ScheduledRunner(
        collection_runner=runner, position_interval=0,
        stablecoin_report_interval=0, dex_liquidity_interval=0,
        reserves_fetch_interval=0, protocols_report_interval=0,
        protocols_refresh_interval=0, snapshots_interval=0,
        risk_monitor_interval=0, screenshot_daily={"enabled": False},
        storage=MagicMock(_session_factory=None),
    )
    sr.start()
    try:
        sr.apply_protocols_refresh_config(interval=1200)
        assert sr._scheduler.get_job("protocols_refresh") is not None
        status = sr.apply_protocols_refresh_config(interval=0)
        assert status == "removed"
        assert sr._scheduler.get_job("protocols_refresh") is None
    finally:
        sr.stop()


@pytest.mark.asyncio
async def test_refresh_job_calls_refresh_all_protocols(tmp_path):
    """The scheduled callable actually invokes refresh_all_protocols."""
    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await s.initialize()
    runner = CollectionRunner(collectors=[], storage=s, wallets=[""])
    sr = ScheduledRunner(
        collection_runner=runner, position_interval=0,
        stablecoin_report_interval=0, dex_liquidity_interval=0,
        reserves_fetch_interval=0, protocols_report_interval=0,
        protocols_refresh_interval=0, snapshots_interval=0,
        risk_monitor_interval=0, screenshot_daily={"enabled": False},
        storage=s,
    )
    sr.start()
    try:
        fake = AsyncMock(return_value={"refreshed": [{"name": "x"}], "failed": []})
        with patch("stake_watch.api.routes.protocols.refresh_all_protocols", fake):
            await sr._refresh_protocols()
        assert fake.await_count == 1
    finally:
        sr.stop()
        await s.close()
