from datetime import datetime, timezone
import pytest
from httpx import ASGITransport, AsyncClient
from stake_watch.api.app import create_app
from stake_watch.models.alert import Alert, Severity, RuleType
from stake_watch.storage.db import Storage

@pytest.fixture
async def client(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    storage = Storage(db_url)
    await storage.initialize()
    # Seed an alert
    await storage.save_alert(Alert(
        rule_type=RuleType.PROTOCOL_EVENT, severity=Severity.WARNING,
        protocol="aave", chain="base", title="Test Alert", message="test",
        created_at=datetime.now(timezone.utc)))
    app = create_app(storage)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await storage.close()

@pytest.mark.asyncio
async def test_list_alerts(client):
    resp = await client.get("/api/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Test Alert"

@pytest.mark.asyncio
async def test_list_alerts_empty(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test2.db"
    storage = Storage(db_url)
    await storage.initialize()
    app = create_app(storage)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/alerts")
    assert resp.status_code == 200
    assert resp.json() == []
    await storage.close()
