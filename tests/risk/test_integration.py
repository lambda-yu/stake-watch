from datetime import datetime, timezone
import pytest
from stake_watch.risk.engine import RuleEngine
from stake_watch.risk.rules import get_default_rules

def test_default_rules_loaded():
    rules = get_default_rules()
    assert len(rules) == 8

def test_full_evaluation_cycle():
    engine = RuleEngine(rules=get_default_rules())
    # Simulate a dangerous context
    ctx = {"protocol": "aave_v3_base", "chain": "base",
           "health_factor": 1.05, "tvl_change_1h": -0.25}
    alerts = engine.evaluate(ctx)
    assert len(alerts) >= 2  # liquidation critical + TVL crash
    severities = {a.severity.value for a in alerts}
    assert "critical" in severities

def test_safe_context_no_alerts():
    engine = RuleEngine(rules=get_default_rules())
    ctx = {"protocol": "aave_v3_base", "chain": "base",
           "health_factor": 2.0, "tvl_change_1h": -0.01, "apy_change_24h": 0.05}
    alerts = engine.evaluate(ctx)
    assert len(alerts) == 0
