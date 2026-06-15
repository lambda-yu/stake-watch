from datetime import datetime, timedelta, timezone
from stake_watch.models.alert import Alert, Severity, RuleType
from stake_watch.risk.engine import RuleEngine, CooldownTracker
from stake_watch.risk.rules.base import BaseRule, RuleContext

class FakeRule(BaseRule):
    rule_type = RuleType.PROTOCOL_EVENT
    severity = Severity.WARNING
    cooldown = timedelta(hours=1)
    def evaluate(self, context: RuleContext) -> Alert | None:
        if context.get("tvl_drop", 0) > 0.15:
            return Alert(rule_type=self.rule_type, severity=self.severity,
                protocol=context["protocol"], chain=context["chain"],
                title="TVL Crash", message=f"TVL dropped {context['tvl_drop']:.0%}",
                created_at=datetime.now(timezone.utc))
        return None

def test_engine_evaluates_rules():
    engine = RuleEngine(rules=[FakeRule()])
    alerts = engine.evaluate({"protocol": "aave", "chain": "base", "tvl_drop": 0.20})
    assert len(alerts) == 1

def test_engine_no_alert_below_threshold():
    engine = RuleEngine(rules=[FakeRule()])
    alerts = engine.evaluate({"protocol": "aave", "chain": "base", "tvl_drop": 0.05})
    assert len(alerts) == 0

def test_cooldown_blocks_duplicate():
    tracker = CooldownTracker()
    a = Alert(rule_type=RuleType.PROTOCOL_EVENT, severity=Severity.WARNING,
        protocol="aave", chain="base", title="TVL", message="t", created_at=datetime.now(timezone.utc))
    assert tracker.should_send(a, timedelta(hours=1)) is True
    tracker.record(a)
    assert tracker.should_send(a, timedelta(hours=1)) is False

def test_cooldown_expires():
    tracker = CooldownTracker()
    old = Alert(rule_type=RuleType.PROTOCOL_EVENT, severity=Severity.WARNING,
        protocol="aave", chain="base", title="TVL", message="t",
        created_at=datetime.now(timezone.utc) - timedelta(hours=2))
    tracker.record(old)
    new = Alert(rule_type=RuleType.PROTOCOL_EVENT, severity=Severity.WARNING,
        protocol="aave", chain="base", title="TVL", message="t",
        created_at=datetime.now(timezone.utc))
    assert tracker.should_send(new, timedelta(hours=1)) is True
