from datetime import datetime, timezone
import pytest
from stake_watch.risk.rules.liquidation import LiquidationWarningRule, LiquidationCriticalRule
from stake_watch.risk.rules.protocol_event import TvlCrashRule, CollectorFailureRule
from stake_watch.risk.rules.yield_change import ApySwingRule
from stake_watch.risk.rules.morpho import MorphoUtilizationRule, MorphoWithdrawalRule, MorphoSharePriceRule

def test_liquidation_warning():
    assert LiquidationWarningRule().evaluate({"protocol": "a", "chain": "b", "health_factor": 1.2}) is not None
def test_liquidation_critical():
    r = LiquidationCriticalRule().evaluate({"protocol": "a", "chain": "b", "health_factor": 1.05})
    assert r is not None and r.severity.value == "critical"
def test_liquidation_safe():
    assert LiquidationWarningRule().evaluate({"protocol": "a", "chain": "b", "health_factor": 1.5}) is None
def test_tvl_crash():
    r = TvlCrashRule().evaluate({"protocol": "a", "chain": "b", "tvl_change_1h": -0.20})
    assert r is not None and r.severity.value == "critical"
def test_tvl_stable():
    assert TvlCrashRule().evaluate({"protocol": "a", "chain": "b", "tvl_change_1h": -0.05}) is None
def test_apy_swing():
    assert ApySwingRule().evaluate({"protocol": "a", "chain": "b", "apy_change_24h": 0.50}) is not None
def test_collector_failure():
    assert CollectorFailureRule().evaluate({"protocol": "a", "chain": "b", "consecutive_failures": 3}) is not None
def test_morpho_utilization():
    assert MorphoUtilizationRule().evaluate({"protocol": "m", "chain": "b", "max_utilization": 0.95}) is not None
def test_morpho_withdrawal_fail():
    r = MorphoWithdrawalRule().evaluate({"protocol": "m", "chain": "b", "can_withdraw_10pct": False, "liquidity_ratio": 0.05})
    assert r is not None and r.severity.value == "critical"
def test_morpho_share_price_drop():
    r = MorphoSharePriceRule().evaluate({"protocol": "m", "chain": "b", "share_price_change": -0.001})
    assert r is not None and r.severity.value == "critical"
