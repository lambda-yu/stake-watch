from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal

from pydantic import BaseModel


class ReserveReport(BaseModel):
    token: str
    issuer: str
    report_date: str
    total_reserves: Decimal
    circulating_supply: Decimal
    coverage_ratio: float
    composition: dict[str, str | float]
    report_cadence_days: int
    days_since_report: int
    is_overdue: bool
    risk_level: str
    updated_at: datetime


REPORT_CADENCE = {"USDC": 30, "USDT": 90}
ISSUERS = {"USDC": "Circle", "USDT": "Tether"}


def evaluate_reserve_risk(
    token: str,
    report_date_str: str | None,
    total_reserves: Decimal | None,
    circulating_supply: Decimal,
    composition: dict[str, float] | None = None,
) -> ReserveReport:
    issuer = ISSUERS.get(token, "Unknown")
    cadence = REPORT_CADENCE.get(token, 90)
    now = datetime.now(timezone.utc)

    if not report_date_str or not total_reserves:
        return ReserveReport(
            token=token, issuer=issuer, report_date="未录入",
            total_reserves=Decimal("0"), circulating_supply=circulating_supply,
            coverage_ratio=0, composition={},
            report_cadence_days=cadence, days_since_report=999,
            is_overdue=True, risk_level="unknown",
            updated_at=now)

    try:
        report_date = datetime.strptime(report_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        report_date = now

    days_since = (now - report_date).days
    is_overdue = days_since > cadence
    coverage = float(total_reserves / circulating_supply) if circulating_supply > 0 else 0

    if coverage < 1.0:
        risk_level = "critical"
    elif is_overdue and days_since > cadence * 2:
        risk_level = "danger"
    elif is_overdue:
        risk_level = "warning"
    elif coverage < 1.02:
        risk_level = "watch"
    else:
        risk_level = "safe"

    return ReserveReport(
        token=token, issuer=issuer, report_date=report_date_str,
        total_reserves=total_reserves, circulating_supply=circulating_supply,
        coverage_ratio=coverage, composition=composition or {},
        report_cadence_days=cadence, days_since_report=days_since,
        is_overdue=is_overdue, risk_level=risk_level,
        updated_at=now)
