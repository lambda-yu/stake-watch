from datetime import datetime, timezone
from decimal import Decimal
import pytest
from stake_watch.models.stablecoin import StablecoinRiskSnapshot
from stake_watch.risk.stablecoin_scorer import StablecoinScorer, ScoreInput
from stake_watch.storage.db import Storage

@pytest.fixture
async def storage(tmp_path):
    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    await s.initialize()
    yield s
    await s.close()

@pytest.mark.asyncio
async def test_full_scoring_pipeline():
    scorer = StablecoinScorer()
    inp = ScoreInput(price=0.997, deviation=0.003, supply_change_24h_pct=-1.5,
        cex_spread_pct=0.15, is_blacklisted=False, cross_chain_verified=True)
    result = scorer.score(inp)
    snap = StablecoinRiskSnapshot(token="USDC", price=0.997, deviation=0.003,
        total_supply=Decimal("75000000000"), supply_change_24h_pct=-1.5,
        supply_change_7d_pct=-3.0, risk_level=result.level, risk_score=result.score,
        hard_trigger=result.hard_trigger, cex_spread_pct=0.15,
        updated_at=datetime.now(timezone.utc))
    assert snap.risk_score > 0
    assert snap.risk_level in ("safe", "watch", "caution")

@pytest.mark.asyncio
async def test_save_and_load_with_score(storage):
    snap = StablecoinRiskSnapshot(token="USDT", price=0.994, deviation=0.006,
        total_supply=Decimal("186000000000"), supply_change_24h_pct=-3.5,
        supply_change_7d_pct=-5.0, risk_level="caution", risk_score=42.5,
        hard_trigger=None, cex_spread_pct=0.3,
        updated_at=datetime.now(timezone.utc))
    await storage.save_stablecoin_snapshot(snap)
    results = await storage.get_latest_stablecoin_snapshots()
    assert len(results) == 1
    assert results[0].risk_score == 42.5
    assert results[0].cex_spread_pct == 0.3
