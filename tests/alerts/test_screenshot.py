"""Tests for screenshot capture helper + Telegram push wrapper.

Playwright is mocked so tests run offline.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------- capture_url_screenshot ----------

@pytest.mark.asyncio
async def test_capture_returns_png_bytes_from_mocked_playwright():
    from stake_watch.alerts.screenshot import capture_url_screenshot

    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.screenshot = AsyncMock(return_value=b"\x89PNG\r\n\x1a\nFAKE")

    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)

    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()

    chromium = MagicMock()
    chromium.launch = AsyncMock(return_value=browser)

    pw_ctx = MagicMock()
    pw_ctx.chromium = chromium

    pw_mgr = MagicMock()
    pw_mgr.__aenter__ = AsyncMock(return_value=pw_ctx)
    pw_mgr.__aexit__ = AsyncMock(return_value=None)

    with patch("playwright.async_api.async_playwright", return_value=pw_mgr):
        png = await capture_url_screenshot(
            "http://test/comparison",
            wait_selector="table tbody tr",
        )
    assert png.startswith(b"\x89PNG")
    page.goto.assert_awaited_once()
    page.wait_for_selector.assert_awaited_once()
    browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_capture_tolerates_selector_timeout():
    """When the wait_selector never appears we still snap (logged warning)."""
    from stake_watch.alerts.screenshot import capture_url_screenshot

    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock(side_effect=Exception("timeout"))
    page.wait_for_timeout = AsyncMock()
    page.screenshot = AsyncMock(return_value=b"PNGDATA")

    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()
    chromium = MagicMock()
    chromium.launch = AsyncMock(return_value=browser)
    pw_ctx = MagicMock(); pw_ctx.chromium = chromium
    pw_mgr = MagicMock()
    pw_mgr.__aenter__ = AsyncMock(return_value=pw_ctx)
    pw_mgr.__aexit__ = AsyncMock(return_value=None)

    with patch("playwright.async_api.async_playwright", return_value=pw_mgr):
        png = await capture_url_screenshot("http://test",
                                            wait_selector="never")
    assert png == b"PNGDATA"


# ---------- send_comparison_screenshot ----------

@pytest.mark.asyncio
async def test_send_returns_error_when_telegram_not_configured(tmp_path):
    from stake_watch.alerts.comparison_screenshot import send_comparison_screenshot
    from stake_watch.storage.db import Storage

    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await s.initialize()
    try:
        r = await send_comparison_screenshot(s)
    finally:
        await s.close()
    assert r["success"] is False
    assert "未配置" in r["error"]


@pytest.mark.asyncio
async def test_send_happy_path_pushes_to_telegram(tmp_path):
    from stake_watch.alerts.comparison_screenshot import send_comparison_screenshot
    from stake_watch.storage.config_store import ConfigStore
    from stake_watch.storage.db import Storage

    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await s.initialize()
    store = ConfigStore(s._session_factory)
    await store.set_setting("telegram.bot_token", "fake-token")
    await store.set_setting("telegram.chat_id", "-1001234")
    await store.set_setting("screenshot.frontend_url", "http://frontend")

    fake_capture = AsyncMock(return_value=b"PNG-OK")
    fake_send = AsyncMock(return_value=True)

    with patch("stake_watch.alerts.comparison_screenshot.capture_url_screenshot",
                 fake_capture), \
         patch("stake_watch.alerts.comparison_screenshot.send_screenshot_to_telegram",
                 fake_send):
        try:
            r = await send_comparison_screenshot(s)
        finally:
            await s.close()

    assert r["success"] is True
    assert r["bytes"] == len(b"PNG-OK")
    # URL was constructed from screenshot.frontend_url + /comparison
    args, kwargs = fake_capture.await_args
    assert args[0] == "http://frontend/comparison"
    # caption passed to send_photo
    _, send_kwargs = fake_send.await_args
    assert "协议对比快照" in send_kwargs.get("caption", "")


@pytest.mark.asyncio
async def test_send_reports_capture_failure(tmp_path):
    from stake_watch.alerts.comparison_screenshot import send_comparison_screenshot
    from stake_watch.storage.config_store import ConfigStore
    from stake_watch.storage.db import Storage

    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await s.initialize()
    store = ConfigStore(s._session_factory)
    await store.set_setting("telegram.bot_token", "x")
    await store.set_setting("telegram.chat_id", "y")

    with patch("stake_watch.alerts.comparison_screenshot.capture_url_screenshot",
                 AsyncMock(side_effect=Exception("net down"))):
        try:
            r = await send_comparison_screenshot(s)
        finally:
            await s.close()

    assert r["success"] is False
    assert "截图失败" in r["error"]


# ---------- /api/comparison/send-telegram + /screenshot-config routes ----------

@pytest.mark.asyncio
async def test_send_telegram_route_calls_helper(tmp_path):
    from httpx import ASGITransport, AsyncClient
    from stake_watch.api.app import create_app
    from stake_watch.storage.db import Storage

    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await s.initialize()
    app = create_app(s)
    try:
        with patch("stake_watch.alerts.comparison_screenshot.send_comparison_screenshot",
                     AsyncMock(return_value={"success": True, "bytes": 100})):
            async with AsyncClient(transport=ASGITransport(app=app),
                                     base_url="http://test") as c:
                r = await c.post("/api/comparison/send-telegram")
                assert r.status_code == 200
                assert r.json()["success"] is True
    finally:
        await s.close()


@pytest.mark.asyncio
async def test_screenshot_config_round_trip(tmp_path):
    from httpx import ASGITransport, AsyncClient
    from stake_watch.api.app import create_app
    from stake_watch.storage.db import Storage

    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await s.initialize()
    app = create_app(s)
    try:
        async with AsyncClient(transport=ASGITransport(app=app),
                                 base_url="http://test") as c:
            r = await c.get("/api/comparison/screenshot-config")
            body = r.json()
            assert body["frontend_url"] == "http://localhost:5173"
            assert body["daily_enabled"] is False
            assert body["daily_hour"] == 9
            assert body["daily_minute"] == 0

            r = await c.put("/api/comparison/screenshot-config",
                             json={"frontend_url": "https://stake.example.com/"})
            assert r.json()["frontend_url"] == "https://stake.example.com"
    finally:
        await s.close()


@pytest.mark.asyncio
async def test_daily_config_round_trip(tmp_path):
    from httpx import ASGITransport, AsyncClient
    from stake_watch.api.app import create_app
    from stake_watch.storage.db import Storage

    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await s.initialize()
    app = create_app(s)
    try:
        async with AsyncClient(transport=ASGITransport(app=app),
                                 base_url="http://test") as c:
            r = await c.put("/api/comparison/screenshot-config",
                             json={"daily_enabled": True, "daily_hour": 21,
                                   "daily_minute": 30})
            body = r.json()
            assert body["daily_enabled"] is True
            assert body["daily_hour"] == 21
            assert body["daily_minute"] == 30
    finally:
        await s.close()


@pytest.mark.asyncio
async def test_daily_config_clamps_out_of_range(tmp_path):
    from httpx import ASGITransport, AsyncClient
    from stake_watch.api.app import create_app
    from stake_watch.storage.db import Storage

    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await s.initialize()
    app = create_app(s)
    try:
        async with AsyncClient(transport=ASGITransport(app=app),
                                 base_url="http://test") as c:
            r = await c.put("/api/comparison/screenshot-config",
                             json={"daily_hour": 99, "daily_minute": -5})
            body = r.json()
            assert body["daily_hour"] == 23
            assert body["daily_minute"] == 0
    finally:
        await s.close()


@pytest.mark.asyncio
async def test_scheduler_registers_daily_cron_when_enabled():
    from stake_watch.scheduler.runner import ScheduledRunner, CollectionRunner

    runner = CollectionRunner(collectors=[], storage=None, wallets=[""])
    sr = ScheduledRunner(
        collection_runner=runner,
        position_interval=0,  # disable interval job for this test
        stablecoin_report_interval=0,
        dex_liquidity_interval=0,
        reserves_fetch_interval=0,
        protocols_report_interval=0,
        snapshots_interval=0,
        risk_monitor_interval=0,
        screenshot_daily={"enabled": True, "hour": 9, "minute": 30, "tz_offset": 8},
        storage=MagicMock(_session_factory=None),
    )
    sr.start()
    try:
        job_ids = {j.id for j in sr._scheduler.get_jobs()}
        assert "screenshot_daily" in job_ids
    finally:
        sr.stop()


@pytest.mark.asyncio
async def test_scheduler_skips_daily_cron_when_disabled():
    from stake_watch.scheduler.runner import ScheduledRunner, CollectionRunner

    runner = CollectionRunner(collectors=[], storage=None, wallets=[""])
    sr = ScheduledRunner(
        collection_runner=runner,
        position_interval=0,
        stablecoin_report_interval=0,
        dex_liquidity_interval=0,
        reserves_fetch_interval=0,
        protocols_report_interval=0,
        snapshots_interval=0,
        risk_monitor_interval=0,
        screenshot_daily={"enabled": False, "hour": 9, "minute": 0, "tz_offset": 8},
        storage=MagicMock(_session_factory=None),
    )
    sr.start()
    try:
        assert "screenshot_daily" not in {j.id for j in sr._scheduler.get_jobs()}
    finally:
        sr.stop()


@pytest.mark.asyncio
async def test_apply_screenshot_daily_config_hot_reload_enables_job():
    """apply_screenshot_daily_config registers + replaces the cron job
    without needing a process restart."""
    from stake_watch.scheduler.runner import ScheduledRunner, CollectionRunner

    runner = CollectionRunner(collectors=[], storage=None, wallets=[""])
    sr = ScheduledRunner(
        collection_runner=runner, position_interval=0,
        stablecoin_report_interval=0, dex_liquidity_interval=0,
        reserves_fetch_interval=0, protocols_report_interval=0,
        snapshots_interval=0, risk_monitor_interval=0,
        screenshot_daily={"enabled": False, "hour": 9, "minute": 0, "tz_offset": 8},
        storage=MagicMock(_session_factory=None),
    )
    sr.start()
    try:
        assert "screenshot_daily" not in {j.id for j in sr._scheduler.get_jobs()}

        # Enable at 21:30 UTC+8 — should register a new cron job
        status = sr.apply_screenshot_daily_config(enabled=True, hour=21,
                                                   minute=30, tz_offset=8)
        assert status == "scheduled"
        job = sr._scheduler.get_job("screenshot_daily")
        assert job is not None
        trigger_repr = str(job.trigger)
        assert "hour='21'" in trigger_repr
        assert "minute='30'" in trigger_repr

        # Change hour to 8 — same job id, replaces existing
        sr.apply_screenshot_daily_config(enabled=True, hour=8, minute=0, tz_offset=8)
        job2 = sr._scheduler.get_job("screenshot_daily")
        assert "hour='8'" in str(job2.trigger)

        # Disable — job is removed
        status = sr.apply_screenshot_daily_config(enabled=False, hour=8,
                                                   minute=0, tz_offset=8)
        assert status == "removed"
        assert sr._scheduler.get_job("screenshot_daily") is None
    finally:
        sr.stop()


@pytest.mark.asyncio
async def test_put_screenshot_config_hot_reloads_scheduler(tmp_path):
    """End-to-end: PUT /api/comparison/screenshot-config triggers the live
    scheduler to add/replace/remove screenshot_daily without restart."""
    from httpx import ASGITransport, AsyncClient
    from stake_watch.api import deps
    from stake_watch.api.app import create_app
    from stake_watch.scheduler.runner import CollectionRunner, ScheduledRunner
    from stake_watch.storage.db import Storage

    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await s.initialize()
    runner = CollectionRunner(collectors=[], storage=s, wallets=[""])
    sr = ScheduledRunner(
        collection_runner=runner, position_interval=0,
        stablecoin_report_interval=0, dex_liquidity_interval=0,
        reserves_fetch_interval=0, protocols_report_interval=0,
        snapshots_interval=0, risk_monitor_interval=0,
        screenshot_daily={"enabled": False}, storage=s,
    )
    sr.start()
    deps.init_scheduler(sr)
    app = create_app(s)
    try:
        async with AsyncClient(transport=ASGITransport(app=app),
                                 base_url="http://test") as c:
            r = await c.put("/api/comparison/screenshot-config",
                             json={"daily_enabled": True, "daily_hour": 12,
                                   "daily_minute": 15})
            body = r.json()
            assert body["daily_enabled"] is True
            assert body["hot_reload"] == "scheduled"
            assert sr._scheduler.get_job("screenshot_daily") is not None

            r = await c.put("/api/comparison/screenshot-config",
                             json={"daily_enabled": False})
            assert r.json()["hot_reload"] == "removed"
            assert sr._scheduler.get_job("screenshot_daily") is None
    finally:
        sr.stop()
        await s.close()
        deps.init_scheduler(None)
