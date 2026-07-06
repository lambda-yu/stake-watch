import pytest
from datetime import datetime, timezone
from stake_watch.alerts.formatter import format_alert, format_tvl
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


@pytest.mark.parametrize("v,expected", [
    (0, "$0"),
    (500, "$500"),
    (999, "$999"),
    (1_000, "$1K"),
    (2_400, "$2K"),
    (999_999, "$1000K"),
    (1_000_000, "$1.0M"),
    (1_200_000, "$1.2M"),
    (999_999_999, "$1000.0M"),
    (1_000_000_000, "$1.00B"),
    (3_400_000_000, "$3.40B"),
])
def test_format_tvl_scales(v, expected):
    assert format_tvl(v) == expected
