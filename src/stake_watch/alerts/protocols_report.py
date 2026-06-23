"""Periodic Telegram report for all monitored staking/lending protocols."""
from __future__ import annotations

import logging

from stake_watch.alerts.timezone import now_display
from stake_watch.storage.db import Storage

logger = logging.getLogger(__name__)


def format_protocols_report(rows: list[dict], tz_offset: int = 8) -> str:
    if not rows:
        return "📊 协议收益定时报告\n━━━━━━━━━━━━━━━━━━━━━━\n暂无数据，请先点击刷新"

    now = now_display(tz_offset)
    lines = [f"📊 协议收益定时报告  {now}", "━━━━━━━━━━━━━━━━━━━━━━"]

    rows = [r for r in rows if r.get("enabled")]
    rows.sort(key=lambda r: -(_best_apy(r) or 0))

    for r in rows:
        name = r["name"]
        primary_chain = r.get("chain", "").upper()
        chains = r.get("chains_breakdown") or []
        lines.append(f"\n• {name}")

        if chains:
            chains_sorted = sorted(chains, key=lambda c: 0 if c["chain"].upper() == primary_chain else 1)
            for c in chains_sorted:
                by_asset = c.get("by_asset") or {}
                usdc = by_asset.get("USDC")
                usdt = by_asset.get("USDT")
                parts = []
                if usdc:
                    parts.append(f"USDC {usdc['apy']:.2f}% / {_format_tvl(usdc['tvl_usd'])}")
                if usdt:
                    parts.append(f"USDT {usdt['apy']:.2f}% / {_format_tvl(usdt['tvl_usd'])}")
                if not parts:
                    other = next(iter(by_asset.items()), None)
                    if other:
                        asset, info = other
                        parts.append(f"{asset} {info['apy']:.2f}% / {_format_tvl(info['tvl_usd'])}")
                    else:
                        parts.append(f"APY {c['apy']:.2f}% / TVL {_format_tvl(c['tvl_usd'])}")
                lines.append(f"  {c['chain']}: {'  '.join(parts)}")
        else:
            apy = r.get("live_apy")
            tvl = r.get("live_tvl_usd")
            asset = r.get("live_pool_asset", "")
            apy_str = f"{apy:.2f}%" if apy is not None else "—"
            tvl_str = _format_tvl(tvl) if tvl else "—"
            lines.append(f"  {primary_chain} {asset}: APY {apy_str}  TVL {tvl_str}")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"共 {len(rows)} 个协议")
    return "\n".join(lines)


def _best_apy(r: dict) -> float | None:
    """Pick the best USDC/USDT APY across chains for sorting."""
    chains = r.get("chains_breakdown") or []
    candidates = []
    for c in chains:
        by_asset = c.get("by_asset") or {}
        for tok in ("USDC", "USDT"):
            info = by_asset.get(tok)
            if info and info.get("apy"):
                candidates.append(info["apy"])
    if candidates:
        return max(candidates)
    return r.get("live_apy")


def _format_tvl(v: float) -> str:
    if v >= 1e9:
        return f"${v/1e9:.2f}B"
    if v >= 1e6:
        return f"${v/1e6:.1f}M"
    if v >= 1e3:
        return f"${v/1e3:.0f}K"
    return f"${v:.0f}"


async def send_protocols_report(storage: Storage):
    from stake_watch.storage.config_store import ConfigStore
    config_store = ConfigStore(storage._session_factory)

    # Refresh latest APY/TVL before composing the report
    try:
        from stake_watch.api.routes.protocols import refresh_all_protocols
        await refresh_all_protocols(store=config_store, storage=storage)
        logger.info("Pre-report refresh completed")
    except Exception as e:
        logger.warning(f"Pre-report refresh failed (using cached data): {e}")

    bot_token = await config_store.get_setting("telegram.bot_token")
    chat_id = await config_store.get_setting("telegram.chat_id")
    if not bot_token or not chat_id:
        return

    tz_offset = await config_store.get_setting("display.timezone_offset") or 8

    protos = await config_store.list_protocols()
    rows = []
    for p in protos:
        stats = await storage.get_latest_protocol_stats(p.name)
        chains = await config_store.get_setting(f"protocols.{p.name}.chains") or []
        live_apy = None
        live_tvl = None
        live_asset = None
        if stats and stats.pools:
            usdc = next((pp for pp in stats.pools if "USDC" in pp.asset.upper()), None)
            default = usdc or stats.pools[0]
            live_apy = default.supply_apy
            live_tvl = float(stats.tvl_usd)
            live_asset = default.asset
        rows.append({
            "name": p.name,
            "chain": p.chain,
            "enabled": p.enabled,
            "safety_score": p.safety_score,
            "live_apy": live_apy,
            "live_tvl_usd": live_tvl,
            "live_pool_asset": live_asset,
            "chains_breakdown": chains,
        })

    text = format_protocols_report(rows, tz_offset=tz_offset)

    try:
        from telegram import Bot
        bot = Bot(token=bot_token)
        await bot.send_message(chat_id=chat_id, text=text)
        logger.info("Protocols report sent to Telegram")
    except Exception as e:
        logger.error(f"Failed to send protocols report: {e}")
