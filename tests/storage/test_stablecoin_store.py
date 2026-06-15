from datetime import datetime, timezone
from decimal import Decimal
import pytest
from stake_watch.models.stablecoin import StablecoinRiskSnapshot
from stake_watch.storage.db import Storage

@pytest.fixture
async def storage(tmp_path):
    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    await s.initialize()
    yield s
    await s.close()

@pytest.mark.asyncio
async def test_save_and_get_stablecoin(storage):
    snap = StablecoinRiskSnapshot(token="USDC", price=0.9998, deviation=0.0002,
        total_supply=Decimal("75000000000"), supply_change_24h_pct=0.67,
        supply_change_7d_pct=2.74, risk_level="safe", updated_at=datetime.now(timezone.utc))
    await storage.save_stablecoin_snapshot(snap)
    results = await storage.get_latest_stablecoin_snapshots()
    assert len(results) == 1
    assert results[0].token == "USDC"
    assert results[0].price == 0.9998
