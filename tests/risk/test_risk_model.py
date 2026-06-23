"""Unit tests for the 8-dimension risk model."""
from __future__ import annotations

import math

import pytest

from stake_watch.risk.risk_model import (
    DIM_KEYS,
    DIM_WEIGHTS,
    DIMENSIONS,
    PRODUCT_RISK,
    PRODUCT_TOTAL,
    _apy_premium_to_score,
    _cap_usage_to_score,
    _default_dims,
    _level,
    _utilization_to_score,
    _withdraw_simulation_bump,
    _withdrawable_ratio_to_score,
    check_veto_rules,
    evaluate,
    get_dim_scores,
)


# ---------- weights / structure invariants ----------

def test_dimension_weights_sum_to_one():
    assert math.isclose(sum(w for _, _, w in DIMENSIONS), 1.0, abs_tol=1e-6)


def test_dim_keys_match_dimensions():
    assert DIM_KEYS == [k for k, _, _ in DIMENSIONS]


def test_curated_products_cover_all_dimensions():
    for key, dims in PRODUCT_RISK.items():
        missing = set(DIM_KEYS) - set(dims)
        assert not missing, f"{key} missing dims: {missing}"


# ---------- _level ----------

@pytest.mark.parametrize("total,expected", [
    (0, "A"), (20, "A"),
    (20.01, "B"), (30, "B"),
    (30.01, "C"), (40, "C"),
    (40.01, "D"), (55, "D"),
    (55.01, "E"), (100, "E"),
])
def test_level_boundaries(total, expected):
    assert _level(total) == expected


# ---------- _default_dims / get_dim_scores ----------

def test_default_dims_uses_asset_chain_lookup():
    d = _default_dims("unknown", "solana", "USDT")
    assert d["stablecoin"] == 18   # USDT default
    assert d["chain"] == 18        # solana default


def test_default_dims_falls_back_for_unknown_chain_asset():
    d = _default_dims("x", "unknownchain", "XYZ")
    assert d["stablecoin"] == 25
    assert d["chain"] == 20


def test_get_dim_scores_returns_curated_for_known_product():
    s = get_dim_scores("aave_v3_base", "base", "USDC")
    assert s["contract"] == 10
    assert s["chain"] == 15


def test_get_dim_scores_falls_back_when_unknown():
    s = get_dim_scores("never_seen", "ethereum", "USDC")
    assert s["stablecoin"] == 12
    assert s["chain"] == 5


def test_get_dim_scores_returns_copy_not_reference():
    s1 = get_dim_scores("aave_v3_base", "base", "USDC")
    s1["contract"] = 999
    s2 = get_dim_scores("aave_v3_base", "base", "USDC")
    assert s2["contract"] == 10


# ---------- _utilization_to_score ----------

@pytest.mark.parametrize("util,expected_score", [
    (0.50, 5), (0.64, 5),
    (0.65, 15), (0.74, 15),
    (0.75, 30), (0.84, 30),
    (0.85, 55), (0.91, 55),
    (0.92, 80), (0.96, 80),
    (0.97, 100), (1.00, 100),
])
def test_utilization_to_score(util, expected_score):
    s, _ = _utilization_to_score(util)
    assert s == expected_score


# ---------- _withdrawable_ratio_to_score ----------

@pytest.mark.parametrize("ratio,expected_score", [
    (0.60, 5), (0.51, 5),
    (0.40, 15), (0.31, 15),
    (0.20, 35), (0.16, 35),
    (0.10, 65), (0.06, 65),
    (0.04, 100), (0.0, 100),
])
def test_withdrawable_ratio_to_score(ratio, expected_score):
    s, _ = _withdrawable_ratio_to_score(ratio)
    assert s == expected_score


# ---------- _withdraw_simulation_bump ----------

def test_withdraw_sim_full_redeem_succeeds():
    extra, notes, w10 = _withdraw_simulation_bump(1.5)
    assert extra == 0
    assert notes == []
    assert w10 is False


def test_withdraw_sim_50pct_failure_only():
    extra, notes, w10 = _withdraw_simulation_bump(0.40)
    assert extra == 30  # 20 (50% fail) + 10 (100% fail)
    assert w10 is False


def test_withdraw_sim_10pct_failure_stacks_all():
    extra, notes, w10 = _withdraw_simulation_bump(0.05)
    assert extra == 70  # 40 + 20 + 10
    assert w10 is True


# ---------- _apy_premium_to_score ----------

@pytest.mark.parametrize("premium,expected_score", [
    (0.0, 5), (0.49, 5),
    (0.5, 20), (1.49, 20),
    (1.5, 45), (2.99, 45),
    (3.0, 70), (4.99, 70),
    (5.0, 100), (10.0, 100),
])
def test_apy_premium_to_score(premium, expected_score):
    s, _ = _apy_premium_to_score(premium)
    assert s == expected_score


# ---------- _cap_usage_to_score ----------

@pytest.mark.parametrize("usage,expected_score", [
    (0.5, 5), (0.7, 20), (0.85, 50), (0.95, 75), (1.0, 100),
])
def test_cap_usage_to_score(usage, expected_score):
    s, _ = _cap_usage_to_score(usage, "Supply")
    assert s == expected_score


# ---------- evaluate() — baseline (no live signals) ----------

def test_evaluate_known_product_uses_product_total():
    r = evaluate("aave_v3_base", "base", "USDC")
    expected = PRODUCT_TOTAL[("aave_v3_base", "base", "USDC")]
    assert r.total == expected
    assert r.level == _level(expected)
    assert r.veto_flags == []
    assert all(d["source"] == "curated" for d in r.dimensions.values())


def test_evaluate_unknown_product_uses_weighted_sum():
    r = evaluate("brand_new_protocol", "ethereum", "USDC")
    expected = sum(_default_dims("brand_new_protocol", "ethereum", "USDC")[k] * w
                   for k, _, w in DIMENSIONS)
    assert math.isclose(r.total, round(expected, 1), abs_tol=0.05)


def test_evaluate_returns_all_dimensions():
    r = evaluate("aave_v3_base", "base", "USDC")
    assert set(r.dimensions.keys()) == set(DIM_KEYS)
    for k, v in r.dimensions.items():
        assert v["weight"] == DIM_WEIGHTS[k]
        assert "score" in v
        assert "label" in v


def test_evaluate_adjusted_yield_linear_and_exp():
    r = evaluate("aave_v3_base", "base", "USDC", apy=5.0)
    assert r.raw_apy == 5.0
    assert math.isclose(r.adjusted_yield_linear, 5.0 * (1 - r.total / 100), abs_tol=0.05)
    assert math.isclose(r.adjusted_yield_exp, 5.0 * math.exp(-2 * r.total / 100), abs_tol=0.05)


def test_evaluate_no_apy_defaults_to_zero():
    r = evaluate("aave_v3_base", "base", "USDC")
    assert r.raw_apy == 0.0
    assert r.adjusted_yield_linear == 0.0


# ---------- evaluate() — live signals ----------

def test_live_utilization_overrides_liquidity_dim():
    r = evaluate("aave_v3_base", "base", "USDC", live_signals={"utilization": 0.96})
    assert r.dimensions["liquidity"]["source"] == "live"
    assert r.dimensions["liquidity"]["score"] == 80


def test_live_withdrawable_ratio_takes_worst_of_with_utilization():
    # withdrawable says critical (100), utilization says modest (15) — worst-of wins
    r = evaluate("aave_v3_base", "base", "USDC",
                 live_signals={"utilization": 0.70, "withdrawable_ratio": 0.03})
    # withdrawable_ratio < 0.10 -> 100 + sim bump 70 = 100 (capped)
    assert r.dimensions["liquidity"]["score"] == 100
    assert r.dimensions["liquidity"]["source"] == "live"


def test_live_bad_debt_overrides_market_dim():
    r = evaluate("aave_v3_base", "base", "USDC",
                 live_signals={"bad_debt_ratio": 0.003})
    assert r.dimensions["market"]["source"] == "live"
    assert r.dimensions["market"]["score"] == 50


def test_live_apy_inverted_forces_market_to_eighty():
    r = evaluate("aave_v3_base", "base", "USDC",
                 live_signals={"apy_inverted": True})
    assert r.dimensions["market"]["score"] >= 80


def test_live_oracle_deviation_overrides_collateral_oracle():
    r = evaluate("aave_v3_base", "base", "USDC",
                 live_signals={"oracle_deviation": 0.04})
    assert r.dimensions["collateral_oracle"]["source"] == "live"
    assert r.dimensions["collateral_oracle"]["score"] == 80


def test_live_oracle_staleness_overrides_collateral_oracle():
    r = evaluate("aave_v3_base", "base", "USDC",
                 live_signals={"oracle_staleness_seconds": 100_000,
                               "oracle_heartbeat_seconds": 86400})
    assert r.dimensions["collateral_oracle"]["source"] == "live"
    # ratio ≈ 1.16 → second tier
    assert r.dimensions["collateral_oracle"]["score"] == 60


def test_live_sequencer_down_pins_chain_to_hundred():
    r = evaluate("aave_v3_base", "base", "USDC",
                 live_signals={"sequencer_down": True,
                               "sequencer_down_seconds": 1200})
    assert r.dimensions["chain"]["score"] == 100
    assert r.dimensions["chain"]["source"] == "live"


def test_live_sequencer_recent_recovery_keeps_chain_elevated():
    r = evaluate("aave_v3_base", "base", "USDC",
                 live_signals={"sequencer_recent_recovery": True})
    assert r.dimensions["chain"]["score"] >= 40
    assert r.dimensions["chain"]["source"] == "live"


def test_live_solana_slot_rate_normal():
    r = evaluate("kamino_usdc", "solana", "USDC",
                 live_signals={"solana_slot_rate": 2.3})
    assert r.dimensions["chain"]["score"] == 18
    assert r.dimensions["chain"]["source"] == "live"


def test_live_solana_slot_rate_severe_slowdown():
    r = evaluate("kamino_usdc", "solana", "USDC",
                 live_signals={"solana_slot_rate": 1.0})
    assert r.dimensions["chain"]["score"] == 90


def test_live_vault_share_price_drop_pins_market_to_hundred():
    r = evaluate("morpho_steakhouse_usdc", "base", "USDC",
                 live_signals={"vault_share_price_dropped": True,
                               "vault_share_price_drop_pct": 0.5})
    assert r.dimensions["market"]["score"] == 100


def test_live_top_depositor_share_overrides_market_dim():
    r = evaluate("morpho_steakhouse_usdc", "base", "USDC",
                 live_signals={"depositor_top1_share": 0.75})
    assert r.dimensions["market"]["source"] == "live"
    assert r.dimensions["market"]["score"] == 75


def test_live_governance_change_recent_pins_governance_high():
    r = evaluate("morpho_steakhouse_usdc", "base", "USDC",
                 live_signals={"governance_change_recent": True})
    assert r.dimensions["governance"]["score"] >= 80
    assert r.dimensions["governance"]["source"] == "live"


def test_live_curator_inactive_30plus_days_bumps_governance():
    r = evaluate("morpho_steakhouse_usdc", "base", "USDC",
                 live_signals={"curator_inactive_days": 45})
    assert r.dimensions["governance"]["score"] >= 60


def test_live_apy_premium_overrides_yield_dim():
    r = evaluate("aave_v3_base", "base", "USDC",
                 live_signals={"apy_premium_pct": 4.0})
    assert r.dimensions["yield"]["source"] == "live"
    assert r.dimensions["yield"]["score"] == 70


def test_live_signals_propagate_to_result_field():
    r = evaluate("aave_v3_base", "base", "USDC",
                 live_signals={"utilization": 0.5})
    assert "utilization" in r.live_signals


def test_live_tvl_drop_24h_overrides_market_when_severe():
    r = evaluate("aave_v3_base", "base", "USDC",
                 live_signals={"tvl_drop_24h": 0.35})
    assert r.dimensions["market"]["score"] == 100


def test_live_tvl_drop_24h_minor_does_not_override():
    r = evaluate("aave_v3_base", "base", "USDC",
                 live_signals={"tvl_drop_24h": 0.05})
    # under 0.08 threshold — falls through to curated
    assert r.dimensions["market"]["source"] == "curated"


def test_evaluate_known_product_delta_adjusts_total():
    base = evaluate("aave_v3_base", "base", "USDC")
    # Adding a live signal that raises liquidity above baseline lifts total
    high = evaluate("aave_v3_base", "base", "USDC",
                    live_signals={"utilization": 0.96})
    assert high.total > base.total


# ---------- check_veto_rules ----------

def test_veto_empty_when_all_healthy():
    assert check_veto_rules() == []


def test_veto_depeg_under_098():
    flags = check_veto_rules(stablecoin_price=0.97)
    assert flags and "0.9700" in flags[0]


def test_veto_no_depeg_at_098():
    assert check_veto_rules(stablecoin_price=0.98) == []


def test_veto_bad_debt_over_threshold():
    flags = check_veto_rules(bad_debt_ratio=0.003)
    assert flags and "坏账率" in flags[0]


def test_veto_share_price_drop():
    assert check_veto_rules(share_price_drop=True) == ["Vault Share Price 下降"]


def test_veto_oracle_deviation_over_3pct():
    flags = check_veto_rules(oracle_deviation=0.04)
    assert flags and "Oracle 偏差" in flags[0]


def test_veto_oracle_stale_beyond_heartbeat_1_5x():
    # heartbeat 1h, age 2h → ratio 2.0 > 1.5 → triggers
    flags = check_veto_rules(oracle_stale_seconds=7200,
                              oracle_heartbeat_seconds=3600)
    assert flags and "Oracle 已停滞" in flags[0]


def test_veto_oracle_stale_below_heartbeat_does_not_trigger():
    flags = check_veto_rules(oracle_stale_seconds=4000,
                              oracle_heartbeat_seconds=3600)
    assert flags == []


def test_veto_utilization_over_97():
    flags = check_veto_rules(utilization=0.98)
    assert flags and "利用率" in flags[0]


def test_veto_withdraw_10pct_failed():
    assert check_veto_rules(withdraw_10_failed=True) == ["10% 提现模拟失败"]


def test_veto_sequencer_down_over_10_minutes():
    flags = check_veto_rules(sequencer_down=True, sequencer_down_seconds=900)
    assert flags and "Sequencer" in flags[0]


def test_veto_sequencer_down_under_10_minutes_no_flag():
    assert check_veto_rules(sequencer_down=True,
                             sequencer_down_seconds=300) == []
