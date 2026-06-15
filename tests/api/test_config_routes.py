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
async def test_list_wallets_empty(client):
    resp = await client.get("/api/config/wallets")
    assert resp.status_code == 200
    assert resp.json() == []

@pytest.mark.asyncio
async def test_add_and_list_wallet(client):
    resp = await client.post("/api/config/wallets", json={"chain": "base", "address": "0xTest", "label": "Test Wallet"})
    assert resp.status_code == 201
    wallet = resp.json()
    assert wallet["chain"] == "base"
    assert wallet["id"] is not None
    resp = await client.get("/api/config/wallets")
    assert len(resp.json()) == 1

@pytest.mark.asyncio
async def test_delete_wallet(client):
    resp = await client.post("/api/config/wallets", json={"chain": "base", "address": "0xTest"})
    wallet_id = resp.json()["id"]
    resp = await client.delete(f"/api/config/wallets/{wallet_id}")
    assert resp.status_code == 204
    resp = await client.get("/api/config/wallets")
    assert len(resp.json()) == 0

@pytest.mark.asyncio
async def test_update_intervals(client):
    resp = await client.put("/api/config/intervals", json={"positions": 60, "protocol_stats": 300})
    assert resp.status_code == 200
    resp = await client.get("/api/config/intervals")
    data = resp.json()
    assert data["positions"] == 60
    assert data["protocol_stats"] == 300
