"""Playwright-driven screenshot capture for Telegram alerts.

Used by the "send Comparison to Telegram" feature and (potentially) any other
page that benefits from a visual snapshot in chat.

Requires a one-shot install:
    uv run playwright install chromium
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def capture_url_screenshot(url: str, *,
                                  wait_selector: str | None = None,
                                  viewport_width: int = 1400,
                                  viewport_height: int = 900,
                                  full_page: bool = True,
                                  timeout_ms: int = 30_000) -> bytes:
    """Render `url` in headless Chromium and return a PNG byte string.

    Args:
        wait_selector: optional CSS selector to wait for before snapping (e.g.
            `table tbody tr` to ensure rows have rendered).
        full_page: if True, captures the whole scrollable page (default).
        timeout_ms: total budget for navigation + selector wait.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as e:
        raise RuntimeError(
            "playwright not installed — run `uv sync` and "
            "`uv run playwright install chromium`"
        ) from e

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                viewport={"width": viewport_width, "height": viewport_height},
                device_scale_factor=2,  # crisp on retina/Telegram
            )
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector,
                                                  timeout=timeout_ms // 2)
                except Exception as e:
                    logger.warning(f"selector {wait_selector!r} not found before snap: {e}")
            png = await page.screenshot(full_page=full_page, type="png")
            return png
        finally:
            await browser.close()


async def send_screenshot_to_telegram(bot_token: str, chat_id: str,
                                        png: bytes,
                                        caption: Optional[str] = None) -> bool:
    """Push a PNG to a Telegram chat. Returns True on success."""
    try:
        from telegram import Bot
        from telegram.constants import ParseMode
        bot = Bot(token=bot_token)
        await bot.send_photo(chat_id=chat_id, photo=png, caption=caption,
                              parse_mode=ParseMode.HTML if caption else None)
        return True
    except Exception as e:
        logger.error(f"Telegram send_photo failed: {e}")
        return False
