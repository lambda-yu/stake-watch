from __future__ import annotations
from decimal import Decimal
from pydantic import BaseModel
from stake_watch.collectors.morpho.models import MorphoMarketAllocation


class BadDebtEstimate(BaseModel):
    market_id: str
    collateral_token: str
    lltv: float
    current_utilization: float
    borrow_assets: Decimal
    supply_assets: Decimal
    estimated_bad_debt_5pct: Decimal   # if collateral drops 5%
    estimated_bad_debt_10pct: Decimal
    estimated_bad_debt_20pct: Decimal
    estimated_bad_debt_30pct: Decimal
    risk_ratio: float  # potential bad debt at -20% / vault total assets


class StressTestResult(BaseModel):
    vault_address: str
    total_vault_assets: Decimal
    markets: list[BadDebtEstimate]
    worst_case_bad_debt_pct: float  # worst market bad_debt_20pct / vault total
    overall_risk: str  # "normal" | "watch" | "warning" | "high_risk" | "critical"


def estimate_bad_debt(
    allocations: list[MorphoMarketAllocation], vault_total_assets: Decimal
) -> StressTestResult:
    """Estimate bad debt for each market based on aggregate utilization and LLTV."""
    estimates: list[BadDebtEstimate] = []
    worst_pct = 0.0

    for alloc in allocations:
        if alloc.borrow_assets <= 0:
            estimates.append(
                BadDebtEstimate(
                    market_id=alloc.market_id,
                    collateral_token=alloc.collateral_token,
                    lltv=alloc.lltv,
                    current_utilization=alloc.utilization,
                    borrow_assets=alloc.borrow_assets,
                    supply_assets=alloc.supply_assets,
                    estimated_bad_debt_5pct=Decimal("0"),
                    estimated_bad_debt_10pct=Decimal("0"),
                    estimated_bad_debt_20pct=Decimal("0"),
                    estimated_bad_debt_30pct=Decimal("0"),
                    risk_ratio=0.0,
                )
            )
            continue

        # For each drop scenario, estimate if aggregate borrowing exceeds
        # what the reduced collateral can cover at LLTV.
        # Simplified: if utilization > lltv after price drop, excess = bad debt.
        borrow = float(alloc.borrow_assets)

        bad_debts: dict[str, Decimal] = {}
        for drop_name, drop_pct in [
            ("5pct", 0.05),
            ("10pct", 0.10),
            ("20pct", 0.20),
            ("30pct", 0.30),
        ]:
            # After collateral drops, effective utilization rises by 1/(1-drop)
            effective_util = (
                alloc.utilization / (1 - drop_pct) if drop_pct < 1 else 1.0
            )
            if effective_util > alloc.lltv and alloc.lltv > 0:
                # Excess borrowing that can't be covered
                excess_ratio = (effective_util - alloc.lltv) / effective_util
                bad_debt = Decimal(str(borrow * excess_ratio))
            else:
                bad_debt = Decimal("0")
            bad_debts[drop_name] = bad_debt

        risk_ratio = (
            float(bad_debts["20pct"] / vault_total_assets)
            if vault_total_assets > 0
            else 0.0
        )
        if risk_ratio > worst_pct:
            worst_pct = risk_ratio

        estimates.append(
            BadDebtEstimate(
                market_id=alloc.market_id,
                collateral_token=alloc.collateral_token,
                lltv=alloc.lltv,
                current_utilization=alloc.utilization,
                borrow_assets=alloc.borrow_assets,
                supply_assets=alloc.supply_assets,
                estimated_bad_debt_5pct=bad_debts["5pct"],
                estimated_bad_debt_10pct=bad_debts["10pct"],
                estimated_bad_debt_20pct=bad_debts["20pct"],
                estimated_bad_debt_30pct=bad_debts["30pct"],
                risk_ratio=risk_ratio,
            )
        )

    overall = "normal"
    if worst_pct > 0.03:
        overall = "critical"
    elif worst_pct > 0.01:
        overall = "high_risk"
    elif worst_pct > 0.005:
        overall = "warning"
    elif worst_pct > 0.001:
        overall = "watch"

    return StressTestResult(
        vault_address=allocations[0].vault_address if allocations else "",
        total_vault_assets=vault_total_assets,
        markets=estimates,
        worst_case_bad_debt_pct=worst_pct,
        overall_risk=overall,
    )
