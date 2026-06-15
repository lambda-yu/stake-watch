from stake_watch.risk.rules.stablecoin import (
    DepegWarningRule, DepegCriticalRule, SupplyChangeRule, StablecoinHardTriggerRule)

def test_depeg_warning():
    r = DepegWarningRule().evaluate({"stablecoin_token": "USDT", "stablecoin_deviation": 0.006})
    assert r is not None and r.severity.value == "warning"

def test_depeg_warning_safe():
    assert DepegWarningRule().evaluate({"stablecoin_token": "USDC", "stablecoin_deviation": 0.002}) is None

def test_depeg_critical():
    r = DepegCriticalRule().evaluate({"stablecoin_token": "USDT", "stablecoin_deviation": 0.015, "stablecoin_price": 0.985})
    assert r is not None and r.severity.value == "critical"

def test_supply_warning():
    r = SupplyChangeRule().evaluate({"stablecoin_token": "USDC", "stablecoin_supply_change_24h_pct": -3.5})
    assert r is not None and r.severity.value == "warning"

def test_supply_critical():
    r = SupplyChangeRule().evaluate({"stablecoin_token": "USDT", "stablecoin_supply_change_24h_pct": -6.0})
    assert r is not None and r.severity.value == "critical"

def test_supply_normal():
    assert SupplyChangeRule().evaluate({"stablecoin_token": "USDC", "stablecoin_supply_change_24h_pct": -1.0}) is None

def test_hard_trigger():
    r = StablecoinHardTriggerRule().evaluate({"stablecoin_token": "USDC", "stablecoin_price": 0.975})
    assert r is not None and "HARD TRIGGER" in r.title

def test_hard_trigger_safe():
    assert StablecoinHardTriggerRule().evaluate({"stablecoin_token": "USDC", "stablecoin_price": 0.999}) is None
