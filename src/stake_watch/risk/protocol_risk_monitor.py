"""Periodic risk monitor: turns risk-model output into Telegram alerts.

Runs `evaluate_protocol_status()` per enabled protocol and emits an Alert when:
1. Veto rules trigger (depeg, bad debt, oracle stale/deviation, sequencer
   down, withdraw-10% fail, share-price drop, etc.) — CRITICAL severity.
2. Risk level escalates (A→B, A→C, …, D→E) compared to the previously
   observed level — WARNING severity (CRITICAL when crossing into E).

Previous level per protocol is persisted in AppSettings under
`risk_monitor.last_level.{name}` so escalation deltas survive restarts.
A cooldown prevents repeating the same dedup key within `cooldown_minutes`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from stake_watch.models.alert import Alert, RuleType, Severity
from stake_watch.risk.products import PRIMARY_PRODUCT
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage

logger = logging.getLogger(__name__)


LEVEL_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}


def _is_escalation(old: str | None, new: str) -> bool:
    if not old or old not in LEVEL_ORDER or new not in LEVEL_ORDER:
        return False
    return LEVEL_ORDER[new] > LEVEL_ORDER[old]


async def _cooldown_blocks(storage: Storage, *, protocol: str, chain: str,
                            kind: str, cooldown_minutes: int) -> bool:
    """Return True when an alert of the given kind for (protocol, chain) fired
    within the cooldown. `kind` is matched against the alert's details so veto
    vs level-escalation can be suppressed independently."""
    if cooldown_minutes <= 0:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
    recent = await storage.get_recent_alerts(limit=200)
    for a in recent:
        if a.protocol != protocol or a.chain != chain:
            continue
        if not a.details or a.details.get("monitor_kind") != kind:
            continue
        created = a.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created >= cutoff:
            return True
    return False


async def run_risk_monitor(storage: Storage, config_store: ConfigStore,
                            cooldown_minutes: int = 360,
                            notifier=None) -> list[Alert]:
    """Evaluate every enabled protocol and emit alerts on veto / level rise.

    Returns the list of Alerts that were created (post-cooldown).
    `notifier` is optional; if provided, each new alert is also pushed.
    """
    from stake_watch.risk.protocol_status import evaluate_protocol_status

    emitted: list[Alert] = []
    protos = await config_store.list_protocols()
    for p in protos:
        if not p.enabled:
            continue
        try:
            status = await evaluate_protocol_status(p.name, storage, config_store)
        except Exception as e:
            logger.warning(f"risk monitor: evaluate_protocol_status({p.name}) failed: {e}")
            continue
        if not status:
            continue
        rm = status.get("risk_model") or {}
        if "error" in rm or "level" not in rm:
            continue

        chain, asset = PRIMARY_PRODUCT.get(p.name, (p.chain, "USDC"))
        veto_flags: list[str] = rm.get("veto_flags") or []
        level = rm.get("level")

        # 1. Veto trigger → CRITICAL alert (one per protocol, msg lists all flags)
        if veto_flags:
            alert = Alert(
                rule_type=RuleType.PROTOCOL_EVENT,
                severity=Severity.CRITICAL,
                protocol=p.name, chain=chain,
                title=f"{p.name} 触发风险否决",
                message="；".join(veto_flags),
                details={"monitor_kind": "veto",
                         "veto_flags": veto_flags, "risk_total": rm.get("total"),
                         "risk_level": level, "primary_asset": asset},
                created_at=datetime.now(timezone.utc),
            )
            if not await _cooldown_blocks(storage, protocol=p.name, chain=chain,
                                           kind="veto",
                                           cooldown_minutes=cooldown_minutes):
                await storage.save_alert(alert)
                emitted.append(alert)
                if notifier is not None:
                    try:
                        await notifier.send(alert)
                    except Exception as e:
                        logger.warning(f"notifier failed for {p.name}: {e}")

        # 2. Risk level escalation → WARNING (or CRITICAL on E)
        last_level = await config_store.get_setting(f"risk_monitor.last_level.{p.name}")
        if _is_escalation(last_level, level):
            severity = Severity.CRITICAL if level == "E" else Severity.WARNING
            alert = Alert(
                rule_type=RuleType.PROTOCOL_EVENT,
                severity=severity,
                protocol=p.name, chain=chain,
                title=f"{p.name} 风险等级 {last_level} → {level}",
                message=f"综合风险评分 {rm.get('total')}，等级从 {last_level} 升至 {level}",
                details={"monitor_kind": "level_escalation",
                         "risk_total": rm.get("total"), "old_level": last_level,
                         "new_level": level, "primary_asset": asset,
                         "veto_flags": veto_flags},
                created_at=datetime.now(timezone.utc),
            )
            if not await _cooldown_blocks(storage, protocol=p.name, chain=chain,
                                           kind="level_escalation",
                                           cooldown_minutes=cooldown_minutes):
                await storage.save_alert(alert)
                emitted.append(alert)
                if notifier is not None:
                    try:
                        await notifier.send(alert)
                    except Exception as e:
                        logger.warning(f"notifier failed for {p.name}: {e}")

        # Always update last-seen level (even if no escalation/cooldown blocked)
        if level:
            await config_store.set_setting(f"risk_monitor.last_level.{p.name}", level)

    return emitted


async def run_risk_monitor_with_telegram(storage: Storage) -> int:
    """Convenience wrapper: read telegram creds, run monitor, push alerts."""
    config_store = ConfigStore(storage._session_factory)
    bot_token = await config_store.get_setting("telegram.bot_token")
    chat_id = await config_store.get_setting("telegram.chat_id")
    cooldown = await config_store.get_setting("risk_monitor.cooldown_minutes") or 360

    notifier = None
    if bot_token and chat_id:
        from stake_watch.alerts.telegram import TelegramNotifier
        notifier = TelegramNotifier(bot_token=bot_token, chat_id=chat_id)

    alerts = await run_risk_monitor(storage, config_store,
                                      cooldown_minutes=int(cooldown),
                                      notifier=notifier)
    return len(alerts)
