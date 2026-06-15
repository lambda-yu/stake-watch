from decimal import Decimal
from stake_watch.collectors.stablecoin.reserves import evaluate_reserve_risk


def test_safe_report():
    r = evaluate_reserve_risk("USDC", "2026-06-10", Decimal("78000000000"),
        Decimal("75000000000"), {"cash": 40, "treasuries": 60})
    assert r.coverage_ratio > 1.02
    assert r.risk_level == "safe"
    assert r.is_overdue is False
    assert r.issuer == "Circle"


def test_coverage_below_100():
    r = evaluate_reserve_risk("USDC", "2026-06-10", Decimal("74000000000"),
        Decimal("75000000000"))
    assert r.coverage_ratio < 1.0
    assert r.risk_level == "critical"


def test_overdue_report():
    r = evaluate_reserve_risk("USDC", "2026-04-01", Decimal("76000000000"),
        Decimal("75000000000"))
    assert r.is_overdue is True
    assert r.days_since_report > 30
    assert r.risk_level in ("warning", "danger")


def test_severely_overdue():
    r = evaluate_reserve_risk("USDT", "2025-01-01", Decimal("190000000000"),
        Decimal("186000000000"))
    assert r.days_since_report > 180
    assert r.risk_level == "danger"


def test_no_report_data():
    r = evaluate_reserve_risk("USDT", None, None, Decimal("186000000000"))
    assert r.risk_level == "unknown"
    assert r.report_date == "未录入"
    assert r.is_overdue is True


def test_usdt_cadence():
    r = evaluate_reserve_risk("USDT", "2026-06-01", Decimal("190000000000"),
        Decimal("186000000000"))
    assert r.report_cadence_days == 90
    assert r.is_overdue is False


def test_composition():
    comp = {"cash": 20, "treasuries": 50, "gold": 15, "bitcoin": 10, "other": 5}
    r = evaluate_reserve_risk("USDT", "2026-06-01", Decimal("190000000000"),
        Decimal("186000000000"), comp)
    assert r.composition["gold"] == 15
    assert sum(r.composition.values()) == 100
