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
async def test_add_and_list_protocols(client):
    resp = await client.post("/api/protocols", json={
        "name": "aave_v3_base", "chain": "base", "collector": "defillama",
        "defillama_slug": "aave-v3", "safety_score": 8.8, "enabled": True})
    assert resp.status_code == 201
    resp = await client.get("/api/protocols")
    protos = resp.json()
    assert len(protos) == 1
    assert protos[0]["name"] == "aave_v3_base"

@pytest.mark.asyncio
async def test_toggle_protocol(client):
    resp = await client.post("/api/protocols", json={
        "name": "test", "chain": "base", "collector": "defillama", "enabled": True})
    proto_id = resp.json()["id"]
    resp = await client.patch(f"/api/protocols/{proto_id}/toggle")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
