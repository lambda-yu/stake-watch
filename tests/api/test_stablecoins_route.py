from datetime import datetime, timezone
from decimal import Decimal
import pytest
from httpx import ASGITransport, AsyncClient
from stake_watch.api.app import create_app
from stake_watch.models.stablecoin import StablecoinRiskSnapshot
from stake_watch.storage.db import Storage

@pytest.fixture
async def client(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    storage = Storage(db_url)
    await storage.initialize()
    await storage.save_stablecoin_snapshot(StablecoinRiskSnapshot(
        token="USDC", price=0.9998, deviation=0.0002, total_supply=Decimal("75000000000"),
        supply_change_24h_pct=0.67, supply_change_7d_pct=2.74, risk_level="safe",
        updated_at=datetime.now(timezone.utc)))
    app = create_app(storage)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await storage.close()

@pytest.mark.asyncio
async def test_get_stablecoins(client):
    resp = await client.get("/api/stablecoins")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["token"] == "USDC"
    assert data[0]["risk_level"] == "safe"
