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

from telegram.ext import ApplicationBuilder, CommandHandler

from stake_watch.alerts.comparison_screenshot import send_comparison_screenshot
from stake_watch.alerts.formatter import format_tvl
from stake_watch.alerts.protocols_report import send_protocols_report
from stake_watch.alerts.timezone import format_time
from stake_watch.storage.config_store import ConfigStore

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


def parse_chat_id(raw) -> int | None:
    """Best-effort convert a stored chat_id setting to int; None on garbage."""
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    # int() accepts leading '-' (channels use negative IDs); refuse floats/text.
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


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

    async def _on_protocols(self, update, context):
        if not self._authorized(update):
            return
        # NOTE: no await between locked() check and `async with` — keeps the
        # check-then-acquire race-free under cooperative scheduling.
        if self._protocols_lock.locked():
            await update.message.reply_text("上一个查询还在跑，请稍等…")
            return
        async with self._protocols_lock:
            await send_protocols_report(self._storage)

    async def _on_compare(self, update, context):
        if not self._authorized(update):
            return
        # NOTE: no await between locked() check and `async with` — keeps the
        # check-then-acquire race-free under cooperative scheduling.
        if self._compare_lock.locked():
            await update.message.reply_text("上一张截图还在生成，请稍等…")
            return
        async with self._compare_lock:
            result = await send_comparison_screenshot(self._storage)
        if not result.get("success"):
            await update.message.reply_text(
                f"截图失败：{result.get('error') or '未知错误'}"
            )

    async def _on_protocol(self, update, context):
        if not self._authorized(update):
            return

        config_store = ConfigStore(self._storage._session_factory)
        protocols = await config_store.list_protocols()
        candidates = ", ".join(p.name for p in protocols) or "(空)"

        arg = " ".join(context.args or []).strip()
        if not arg:
            await update.message.reply_text(
                f"用法: /protocol <名字>\n可用: {candidates}"
            )
            return

        match = next(
            (p for p in protocols if p.name.lower() == arg.lower()),
            None,
        )
        if match is None:
            await update.message.reply_text(
                f"未找到 '{arg}'。可用: {candidates}"
            )
            return

        chains = await config_store.get_setting(f"protocols.{match.name}.chains")
        stats = await self._storage.get_latest_protocol_stats(match.name)
        tz_offset = await config_store.get_setting("display.timezone_offset") or 8

        text = format_protocol_detail(
            protocol=match,
            chains_breakdown=chains,
            stats=stats,
            tz_offset=int(tz_offset),
        )
        await update.message.reply_text(text)

    async def _on_error(self, update, context):
        logger.error(
            "telegram: handler error: %s",
            getattr(context, "error", None),
            exc_info=getattr(context, "error", None),
        )
        if update is None:
            return
        if not self._authorized(update):
            return
        try:
            await update.message.reply_text("处理命令时出错，请查看服务日志")
        except Exception:
            # reply_text can itself fail (Telegram rate limit, network) —
            # swallow to preserve the error-handler contract.
            logger.exception("telegram: failed to notify user of error")

    async def run(self):
        self._app = ApplicationBuilder().token(self._bot_token).build()
        self._app.add_handler(CommandHandler("help", self._on_help))
        self._app.add_handler(CommandHandler("protocols", self._on_protocols))
        self._app.add_handler(CommandHandler("compare", self._on_compare))
        self._app.add_handler(CommandHandler("protocol", self._on_protocol))
        self._app.add_error_handler(self._on_error)

        await self._app.initialize()
        try:
            await self._app.bot.set_my_commands([
                ("help", "显示帮助"),
                ("protocols", "全部协议 APY / TVL 概览"),
                ("compare", "协议对比页面截图"),
                ("protocol", "单个协议详情：/protocol <名字>"),
            ])
        except Exception:
            logger.warning("telegram: set_my_commands failed", exc_info=True)

        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        try:
            await self._stopped.wait()
        finally:
            # Best-effort stop in case cancellation reaches us here.
            await self.stop()

    async def stop(self):
        if self._shutdown_done:
            self._stopped.set()
            return
        if self._app is None:
            self._shutdown_done = True
            self._stopped.set()
            return
        self._shutdown_done = True
        try:
            updater = getattr(self._app, "updater", None)
            if updater is not None and getattr(updater, "running", False):
                await updater.stop()
            if getattr(self._app, "running", False):
                await self._app.stop()
            await self._app.shutdown()
        finally:
            self._stopped.set()
