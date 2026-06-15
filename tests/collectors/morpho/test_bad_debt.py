from decimal import Decimal
import pytest
from stake_watch.collectors.morpho.bad_debt import estimate_bad_debt, BadDebtEstimate
from stake_watch.collectors.morpho.models import MorphoMarketAllocation


def _alloc(
    util: float, lltv: float, borrow: str = "800000", supply: str = "1000000"
) -> MorphoMarketAllocation:
    return MorphoMarketAllocation(
        vault_address="0xV",
        market_id="0xM",
        loan_token="USDC",
        collateral_token="WETH",
        oracle="0xO",
        irm="0xI",
        lltv=lltv,
        supply_assets=Decimal(supply),
        borrow_assets=Decimal(borrow),
        liquidity=Decimal(supply) - Decimal(borrow),
        utilization=util,
        allocation_percent=100.0,
    )


def test_safe_market():
    result = estimate_bad_debt([_alloc(0.5, 0.86)], Decimal("1000000"))
    assert result.markets[0].estimated_bad_debt_20pct == Decimal("0")
    assert result.overall_risk == "normal"


def test_high_util_bad_debt():
    # 80% utilization with 86% LLTV — at -20% drop, effective util = 0.8/0.8 = 1.0 > 0.86
    result = estimate_bad_debt([_alloc(0.80, 0.86)], Decimal("1000000"))
    assert result.markets[0].estimated_bad_debt_20pct > 0


def test_no_borrows():
    alloc = _alloc(0.0, 0.86, borrow="0")
    result = estimate_bad_debt([alloc], Decimal("1000000"))
    assert result.markets[0].estimated_bad_debt_30pct == Decimal("0")


def test_multiple_markets():
    allocs = [_alloc(0.5, 0.86), _alloc(0.85, 0.86)]
    result = estimate_bad_debt(allocs, Decimal("2000000"))
    assert len(result.markets) == 2
    # Second market has higher risk
    assert (
        result.markets[1].estimated_bad_debt_10pct
        >= result.markets[0].estimated_bad_debt_10pct
    )


def test_critical_risk():
    # Very high utilization
    result = estimate_bad_debt(
        [_alloc(0.84, 0.86, borrow="840000", supply="1000000")], Decimal("100000")
    )
    assert result.worst_case_bad_debt_pct > 0
