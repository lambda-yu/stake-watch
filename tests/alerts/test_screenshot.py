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
            assert r.json()["frontend_url"] == "http://localhost:5173"
            r = await c.put("/api/comparison/screenshot-config",
                             json={"frontend_url": "https://stake.example.com/"})
            assert r.json()["frontend_url"] == "https://stake.example.com"  # trailing / stripped
    finally:
        await s.close()
