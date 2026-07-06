"""Interactive Telegram command bot (long polling).

Runs alongside FastAPI + APScheduler as a third asyncio task in the main
process. Only messages from the configured `telegram.chat_id` are processed;
other chats are ignored silently.

Commands:
  /help              — command list
  /protocols         — trigger the full protocols report
  /compare           — trigger the comparison-page screenshot
  /protocol <name>   — single-protocol detail (case-insensitive match)
"""
from __future__ import annotations


def format_help() -> str:
    return (
        "🤖 Stake Watch 命令\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "/protocols  — 全部协议 APY / TVL 概览\n"
        "/compare    — 协议对比页面截图\n"
        "/protocol <名字>  — 单个协议详情\n"
        "/help       — 显示此帮助"
    )
