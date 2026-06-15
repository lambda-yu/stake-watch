from datetime import datetime, timezone
from decimal import Decimal
import pytest
from httpx import ASGITransport, AsyncClient
from stake_watch.api.app import create_app
from stake_watch.storage.db import Storage


@pytest.fixture
async def client(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    storage = Storage(db_url)
    await storage.initialize()
    app = create_app(storage)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await storage.close()


@pytest.mark.asyncio
async def test_get_report_config_default(client):
    resp = await client.get("/api/stablecoins/report-config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["interval"] == 3600
    assert data["enabled"] is True


@pytest.mark.asyncio
async def test_update_report_config(client):
    resp = await client.put("/api/stablecoins/report-config", json={"interval": 7200, "enabled": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["interval"] == 7200
    assert data["enabled"] is False

    resp = await client.get("/api/stablecoins/report-config")
    data = resp.json()
    assert data["interval"] == 7200
    assert data["enabled"] is False
