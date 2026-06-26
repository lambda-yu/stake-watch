"""Send a screenshot of the Comparison page to the configured Telegram chat.

Triggered manually from the Comparison page button or via
`POST /api/comparison/send-telegram`. Optionally scheduled.
"""
from __future__ import annotations

import logging

from stake_watch.alerts.screenshot import (
    capture_url_screenshot,
    send_screenshot_to_telegram,
)
from stake_watch.alerts.timezone import now_display
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage

logger = logging.getLogger(__name__)


async def send_comparison_screenshot(storage: Storage) -> dict:
    """Capture /comparison from the configured frontend URL and push to Telegram.

    Returns {"success": bool, "error"?: str}.
    Configuration (all via Settings → AppSettings):
      - screenshot.frontend_url (default http://localhost:5173)
      - telegram.bot_token / telegram.chat_id
      - display.timezone_offset (for caption timestamp)
    """
    config_store = ConfigStore(storage._session_factory)

    bot_token = await config_store.get_setting("telegram.bot_token")
    chat_id = await config_store.get_setting("telegram.chat_id")
    if not bot_token or not chat_id:
        return {"success": False, "error": "Telegram bot_token / chat_id 未配置"}

    base_url = (await config_store.get_setting("screenshot.frontend_url")
                or "http://localhost:5173")
    base_url = base_url.rstrip("/")
    target_url = f"{base_url}/comparison"

    try:
        png = await capture_url_screenshot(
            target_url,
            wait_selector="table tbody tr",   # ensure rows have rendered
            viewport_width=1400,
            viewport_height=1100,
            full_page=True,
            timeout_ms=45_000,
        )
    except RuntimeError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"capture failed: {e}")
        return {"success": False, "error": f"截图失败: {e}"}

    tz_offset = await config_store.get_setting("display.timezone_offset") or 8
    caption = f"📊 协议对比快照  {now_display(tz_offset)}"

    ok = await send_screenshot_to_telegram(bot_token, chat_id, png, caption=caption)
    if not ok:
        return {"success": False, "error": "Telegram 推送失败，请查看服务日志"}
    logger.info("Comparison screenshot pushed to Telegram")
    return {"success": True, "bytes": len(png)}
