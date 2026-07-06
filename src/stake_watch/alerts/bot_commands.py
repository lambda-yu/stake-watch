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

import asyncio
import logging
from typing import Any

from stake_watch.alerts.formatter import format_tvl
from stake_watch.alerts.timezone import format_time

logger = logging.getLogger(__name__)


_MAX_MESSAGE_CHARS = 3800  # Telegram hard limit is 4096; leave headroom.


def format_help() -> str:
    return (
        "🤖 Stake Watch 命令\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "/protocols  — 全部协议 APY / TVL 概览\n"
        "/compare    — 协议对比页面截图\n"
        "/protocol <名字>  — 单个协议详情\n"
        "/help       — 显示此帮助"
    )


def format_protocol_detail(
    protocol: dict[str, Any],
    chains_breakdown: list[dict] | None,
    stats: Any,
    tz_offset: int = 8,
) -> str:
    """Compose the single-protocol detail message body.

    ``protocol`` is a mapping (or ORM row exposing attribute access via .name,
    .chain, .enabled, .safety_score, .risk_scores). ``chains_breakdown`` is
    the per-chain / per-asset structure stored under
    ``protocols.<name>.chains``. ``stats`` may be None or an object with a
    ``.timestamp`` attribute (a UTC-aware ``datetime``).

    Returns a plain-text message body, truncated to Telegram's per-message
    limit if necessary.
    """
    p = _view(protocol)
    lines: list[str] = [f"📋 {p['name']}", "━━━━━━━━━━━━━━━━━━━━━━"]

    lines.append(f"链: {p.get('chain') or '?'}")
    lines.append(f"状态: {'启用 ✓' if p.get('enabled') else '停用 ✗'}")

    safety = p.get("safety_score")
    if safety is not None:
        lines.append(f"Safety Score: {safety}")

    if chains_breakdown:
        lines.append("")
        lines.append("各链池子:")
        primary_chain = (p.get("chain") or "").upper()
        chains_sorted = sorted(
            chains_breakdown,
            key=lambda c: 0 if (c.get("chain") or "").upper() == primary_chain else 1,
        )
        for c in chains_sorted:
            lines.append(f"  {c.get('chain', '?')}")
            by_asset = c.get("by_asset") or {}
            for asset in _ordered_assets(by_asset):
                info = by_asset[asset]
                apy = info.get("apy")
                tvl = info.get("tvl_usd")
                apy_str = f"{apy:.2f}%" if apy is not None else "—"
                tvl_str = format_tvl(tvl) if tvl else "—"
                lines.append(f"    {asset}  APY {apy_str}  TVL {tvl_str}")
    elif stats is not None and getattr(stats, "pools", None):
        # fallback: single-chain / single-pool from ProtocolStats
        lines.append("")
        default = _pick_default_pool(stats.pools)
        asset = default.asset
        apy = getattr(default, "supply_apy", None)
        tvl = getattr(stats, "tvl_usd", None)
        apy_str = f"{apy:.2f}%" if apy is not None else "—"
        tvl_str = format_tvl(float(tvl)) if tvl else "—"
        lines.append(
            f"{(p.get('chain') or '').upper()} {asset}: APY {apy_str}  TVL {tvl_str}"
        )

    risk = p.get("risk_scores") or {}
    if isinstance(risk, dict) and risk:
        parts = [f"{k} {v}" for k, v in risk.items()]
        lines.append("")
        lines.append("风险评分: " + " / ".join(parts))

    ts = getattr(stats, "timestamp", None) if stats is not None else None
    if ts is not None:
        lines.append("")
        lines.append(f"最新数据: {format_time(ts, tz_offset)}")

    body = "\n".join(lines)
    if len(body) > _MAX_MESSAGE_CHARS:
        body = body[: _MAX_MESSAGE_CHARS - 20].rstrip() + "\n...(已截断)"
    return body


def _view(protocol: Any) -> dict:
    """Uniform dict view over ORM row or plain dict."""
    if isinstance(protocol, dict):
        return protocol
    return {
        "name": getattr(protocol, "name", None),
        "chain": getattr(protocol, "chain", None),
        "enabled": getattr(protocol, "enabled", None),
        "safety_score": getattr(protocol, "safety_score", None),
        "risk_scores": getattr(protocol, "risk_scores", None),
    }


def _ordered_assets(by_asset: dict) -> list[str]:
    """USDC first, USDT second, then anything else in dict order."""
    preferred = [a for a in ("USDC", "USDT") if a in by_asset]
    others = [a for a in by_asset if a not in preferred]
    return preferred + others


def _pick_default_pool(pools):
    """USDC-preferring pool selector; falls back to first pool."""
    for pool in pools:
        if "USDC" in (getattr(pool, "asset", "") or "").upper():
            return pool
    return pools[0]


class TelegramCommandBot:
    """Long-polling command bot; runs as an asyncio task in main.py."""

    def __init__(self, bot_token: str, chat_id: int, storage):
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._storage = storage
        self._app = None
        self._stopped = asyncio.Event()
        self._shutdown_done = False
        self._protocols_lock = asyncio.Lock()
        self._compare_lock = asyncio.Lock()

    def _authorized(self, update) -> bool:
        chat = getattr(update, "effective_chat", None)
        if chat is None or chat.id != self._chat_id:
            if chat is not None:
                logger.info(
                    "telegram: unauthorized chat_id=%s (expected %s)",
                    chat.id,
                    self._chat_id,
                )
            return False
        return True

    async def _on_help(self, update, context):
        if not self._authorized(update):
            return
        await update.message.reply_text(format_help())
