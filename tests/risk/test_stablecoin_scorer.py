from decimal import Decimal
import pytest
from stake_watch.risk.stablecoin_scorer import StablecoinScorer, ScoreInput

def test_safe_score():
    inp = ScoreInput(price=0.9999, deviation=0.0001, supply_change_24h_pct=-0.5,
        supply_change_7d_pct=-1.0, cex_spread_pct=0.01,
        is_blacklisted=False, cross_chain_verified=True, cross_chain_risk_premium=0)
    scorer = StablecoinScorer()
    result = scorer.score(inp)
    assert result.score < 20
    assert result.level == "safe"

def test_caution_score():
    inp = ScoreInput(price=0.996, deviation=0.004, supply_change_24h_pct=-2.5,
        supply_change_7d_pct=-4.0, cex_spread_pct=0.3,
        is_blacklisted=False, cross_chain_verified=True, cross_chain_risk_premium=0)
    scorer = StablecoinScorer()
    result = scorer.score(inp)
    assert 20 <= result.score < 50
    assert result.level in ("watch", "caution")

def test_danger_score():
    inp = ScoreInput(price=0.985, deviation=0.015, supply_change_24h_pct=-6.0,
        supply_change_7d_pct=-10.0, cex_spread_pct=1.5,
        is_blacklisted=False, cross_chain_verified=True, cross_chain_risk_premium=0)
    scorer = StablecoinScorer()
    result = scorer.score(inp)
    assert result.score >= 50
    assert result.level in ("danger", "critical")

def test_hard_trigger_price():
    inp = ScoreInput(price=0.975, deviation=0.025, supply_change_24h_pct=0,
        supply_change_7d_pct=0, cex_spread_pct=0,
        is_blacklisted=False, cross_chain_verified=True, cross_chain_risk_premium=0)
    scorer = StablecoinScorer()
    result = scorer.score(inp)
    assert result.score == 100
    assert result.level == "critical"
    assert result.hard_trigger is not None

def test_hard_trigger_blacklisted():
    inp = ScoreInput(price=1.0, deviation=0.0, supply_change_24h_pct=0,
        supply_change_7d_pct=0, cex_spread_pct=0,
        is_blacklisted=True, cross_chain_verified=True, cross_chain_risk_premium=0)
    scorer = StablecoinScorer()
    result = scorer.score(inp)
    assert result.score == 100
    assert result.hard_trigger == "wallet_blacklisted"

def test_unverified_cross_chain():
    inp = ScoreInput(price=1.0, deviation=0.0, supply_change_24h_pct=0,
        supply_change_7d_pct=0, cex_spread_pct=0,
        is_blacklisted=False, cross_chain_verified=False, cross_chain_risk_premium=100)
    scorer = StablecoinScorer()
    result = scorer.score(inp)
    assert result.score > 0  # Cross-chain risk adds to score
