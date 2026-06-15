from stake_watch.risk.rules.morpho import MorphoBadDebtRule, MorphoGovernanceRule


def test_bad_debt_warning():
    r = MorphoBadDebtRule().evaluate(
        {"protocol": "m", "chain": "b", "worst_case_bad_debt_pct": 0.015}
    )
    assert r is not None and r.severity.value == "warning"


def test_bad_debt_critical():
    r = MorphoBadDebtRule().evaluate(
        {"protocol": "m", "chain": "b", "worst_case_bad_debt_pct": 0.05}
    )
    assert r is not None and r.severity.value == "critical"


def test_bad_debt_safe():
    assert (
        MorphoBadDebtRule().evaluate(
            {"protocol": "m", "chain": "b", "worst_case_bad_debt_pct": 0.005}
        )
        is None
    )


def test_governance_critical():
    events = [{"event_type": "SetCurator"}]
    r = MorphoGovernanceRule().evaluate(
        {"protocol": "m", "chain": "b", "governance_events": events}
    )
    assert r is not None and r.severity.value == "critical"


def test_governance_info():
    events = [{"event_type": "SetFee"}]
    r = MorphoGovernanceRule().evaluate(
        {"protocol": "m", "chain": "b", "governance_events": events}
    )
    assert r is not None and r.severity.value == "info"


def test_governance_no_events():
    assert (
        MorphoGovernanceRule().evaluate(
            {"protocol": "m", "chain": "b", "governance_events": []}
        )
        is None
    )
