from __future__ import annotations
from datetime import datetime, timedelta, timezone
from stake_watch.models.alert import Alert, Severity
from stake_watch.risk.rules.base import BaseRule, RuleContext

COOLDOWN_MAP = {
    Severity.CRITICAL: timedelta(minutes=15),
    Severity.WARNING: timedelta(hours=1),
    Severity.INFO: timedelta(hours=6),
}


class CooldownTracker:
    def __init__(self):
        self._last_sent: dict[str, datetime] = {}

    def should_send(self, alert: Alert, cooldown: timedelta | None = None) -> bool:
        cd = cooldown or COOLDOWN_MAP.get(alert.severity, timedelta(hours=1))
        last = self._last_sent.get(alert.dedup_key)
        if last is None:
            return True
        return (datetime.now(timezone.utc) - last) >= cd

    def record(self, alert: Alert):
        self._last_sent[alert.dedup_key] = alert.created_at


class RuleEngine:
    def __init__(self, rules: list[BaseRule] | None = None):
        self.rules = rules or []
        self.cooldown = CooldownTracker()

    def evaluate(self, context: RuleContext) -> list[Alert]:
        alerts = []
        for rule in self.rules:
            try:
                alert = rule.evaluate(context)
                if alert and self.cooldown.should_send(alert, rule.cooldown):
                    alerts.append(alert)
                    self.cooldown.record(alert)
            except Exception:
                pass
        return alerts
