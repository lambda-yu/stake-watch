from datetime import datetime, timezone
from stake_watch.models.alert import Alert, Severity, RuleType

def test_alert_creation():
    a = Alert(rule_type=RuleType.LIQUIDATION, severity=Severity.CRITICAL,
        protocol="jupiter_lend", chain="solana", title="Liquidation Risk",
        message="Health factor 1.08", details={"health_factor": 1.08},
        created_at=datetime.now(timezone.utc))
    assert a.severity == Severity.CRITICAL

def test_alert_dedup_key():
    a = Alert(rule_type=RuleType.LIQUIDATION, severity=Severity.WARNING,
        protocol="aave_v3_base", chain="base", title="Test", message="test",
        created_at=datetime.now(timezone.utc))
    assert a.dedup_key == "liquidation:aave_v3_base:base"
