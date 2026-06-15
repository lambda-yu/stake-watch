from datetime import datetime, timezone
from stake_watch.alerts.formatter import format_alert
from stake_watch.models.alert import Alert, Severity, RuleType

def test_format_critical():
    a = Alert(rule_type=RuleType.LIQUIDATION, severity=Severity.CRITICAL,
        protocol="jupiter_lend", chain="solana", title="Liquidation Risk",
        message="Health factor 1.08", details={"health_factor": 1.08},
        created_at=datetime.now(timezone.utc))
    text = format_alert(a)
    assert "[CRITICAL]" in text
    assert "Liquidation Risk" in text
    assert "jupiter_lend" in text

def test_format_warning():
    a = Alert(rule_type=RuleType.PROTOCOL_EVENT, severity=Severity.WARNING,
        protocol="aave_v3_base", chain="base", title="TVL Drop",
        message="TVL dropped 20%", created_at=datetime.now(timezone.utc))
    text = format_alert(a)
    assert "[WARNING]" in text
    assert "aave_v3_base" in text

def test_format_info():
    a = Alert(rule_type=RuleType.YIELD_CHANGE, severity=Severity.INFO,
        protocol="aave", chain="base", title="APY Change",
        message="APY increased 40%", created_at=datetime.now(timezone.utc))
    text = format_alert(a)
    assert "[INFO]" in text
