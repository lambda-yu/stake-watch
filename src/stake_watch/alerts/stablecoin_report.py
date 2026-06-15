from __future__ import annotations

import logging
from datetime import datetime, timezone

from stake_watch.alerts.timezone import now_display, format_time
from stake_watch.storage.db import Storage

logger = logging.getLogger(__name__)

RISK_EMOJI = {"safe": "🟢", "watch": "🟡", "caution": "🟠", "danger": "🔴", "critical": "🔴🔴"}
RISK_LABEL = {"safe": "安全", "watch": "关注", "caution": "注意", "danger": "危险", "critical": "严重"}


def format_stablecoin_report(snapshots: list, tz_offset: int = 8,
                              dex_pools: list | None = None,
                              reserves: list | None = None) -> str:
    if not snapshots:
        return "📊 稳定币定时报告\n━━━━━━━━━━━━━━━━━━━━━━\n暂无数据"

    now = now_display(tz_offset)
    lines = [f"📊 稳定币定时报告  {now}", "━━━━━━━━━━━━━━━━━━━━━━"]

    for s in snapshots:
        token = s.token
        emoji = RISK_EMOJI.get(s.risk_level, "⚪")
        label = RISK_LABEL.get(s.risk_level, s.risk_level)
        score_str = f" ({s.risk_score:.0f}/100)" if s.risk_score > 0 else ""

        lines.append(f"\n{emoji} {token}  {label}{score_str}")
        lines.append(f"  价格: ${s.price:.4f}  偏离: {s.deviation * 100:.3f}%")

        supply_b = float(s.total_supply) / 1e9
        lines.append(f"  总供应: ${supply_b:.1f}B")

        change_24h = s.supply_change_24h_pct
        change_7d = s.supply_change_7d_pct
        arrow_24h = "📈" if change_24h > 0 else "📉" if change_24h < 0 else "➡️"
        arrow_7d = "📈" if change_7d > 0 else "📉" if change_7d < 0 else "➡️"
        lines.append(f"  24h: {arrow_24h} {change_24h:+.2f}%  7d: {arrow_7d} {change_7d:+.2f}%")

        if hasattr(s, 'cex_spread_pct') and s.cex_spread_pct > 0:
            lines.append(f"  CEX价差: {s.cex_spread_pct:.3f}%")

        if hasattr(s, 'hard_trigger') and s.hard_trigger:
            lines.append(f"  ⚠️ 硬触发: {s.hard_trigger}")

        if hasattr(s, 'updated_at') and s.updated_at:
            lines.append(f"  采集: {format_time(s.updated_at, tz_offset)}")

    if dex_pools:
        lines.append("\n📊 DEX 流动性")
        for p in dex_pools:
            tvl_m = float(p.reserve_usd) / 1e6
            vol_m = float(p.volume_24h_usd) / 1e6
            lines.append(f"  {p.pool_name}: TVL ${tvl_m:.1f}M  24h量 ${vol_m:.1f}M  滑点(1M) {p.estimated_slippage_1m:.2f}%")

    if reserves:
        lines.append("\n🏦 发行方储备")
        for r in reserves:
            if isinstance(r, dict):
                token = r.get("token", "?")
                coverage = r.get("coverage_ratio", 0)
                days = r.get("days_since_report", 999)
                risk = RISK_LABEL.get(r.get("risk_level", ""), r.get("risk_level", ""))
                coverage_str = f"{coverage * 100:.1f}%" if coverage > 0 else "未知"
                days_str = f"{days}天" if days < 999 else "未录入"
                overdue = " ⚠逾期" if r.get("is_overdue") and days < 999 else ""
                lines.append(f"  {token} ({r.get('issuer', '')}): 覆盖率 {coverage_str}  报告距今 {days_str}{overdue}  {risk}")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


async def send_stablecoin_report(storage: Storage):
    from stake_watch.storage.config_store import ConfigStore
    config_store = ConfigStore(storage._session_factory)

    bot_token = await config_store.get_setting("telegram.bot_token")
    chat_id = await config_store.get_setting("telegram.chat_id")
    if not bot_token or not chat_id:
        return

    tz_offset = await config_store.get_setting("display.timezone_offset") or 8
    snapshots = await storage.get_latest_stablecoin_snapshots()
    if not snapshots:
        return

    dex_pools = None
    try:
        from stake_watch.collectors.stablecoin.dex_liquidity import DexLiquidityCollector
        collector = DexLiquidityCollector()
        dex_pools = await collector.collect_pools()
    except Exception:
        pass

    reserves = None
    try:
        from stake_watch.collectors.stablecoin.reserves import evaluate_reserve_risk
        from decimal import Decimal
        supply_map = {s.token: s.total_supply for s in snapshots}
        reserve_list = []
        for token in ["USDC", "USDT"]:
            report_date = await config_store.get_setting(f"reserves.{token.lower()}.report_date")
            total_raw = await config_store.get_setting(f"reserves.{token.lower()}.total_reserves")
            total = Decimal(str(total_raw)) if total_raw else None
            composition = await config_store.get_setting(f"reserves.{token.lower()}.composition") or {}
            circ = supply_map.get(token, Decimal("0"))
            r = evaluate_reserve_risk(token, report_date, total, circ, composition)
            reserve_list.append(r.model_dump())
        reserves = reserve_list
    except Exception:
        pass

    text = format_stablecoin_report(snapshots, tz_offset=tz_offset,
                                     dex_pools=dex_pools, reserves=reserves)

    try:
        from telegram import Bot
        bot = Bot(token=bot_token)
        await bot.send_message(chat_id=chat_id, text=text)
        logger.info("Stablecoin report sent to Telegram")
    except Exception as e:
        logger.error(f"Failed to send stablecoin report: {e}")
