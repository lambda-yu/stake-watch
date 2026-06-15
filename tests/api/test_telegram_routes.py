from datetime import datetime, timezone
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
async def test_telegram_get_unconfigured(client):
    resp = await client.get("/api/config/telegram")
    assert resp.status_code == 200
    data = resp.json()
    assert data["bot_token"] == ""
    assert data["chat_id"] == ""
    assert data["configured"] is False


@pytest.mark.asyncio
async def test_telegram_update(client):
    resp = await client.put("/api/config/telegram", json={
        "bot_token": "123:ABC", "chat_id": "-100123"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["bot_token"] == "123:ABC"
    assert data["chat_id"] == "-100123"
    assert data["configured"] is True


@pytest.mark.asyncio
async def test_telegram_get_after_update(client):
    await client.put("/api/config/telegram", json={
        "bot_token": "token", "chat_id": "chat"
    })
    resp = await client.get("/api/config/telegram")
    data = resp.json()
    assert data["configured"] is True


@pytest.mark.asyncio
async def test_telegram_test_unconfigured(client):
    resp = await client.post("/api/config/telegram/test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "未配置" in data["error"]


@pytest.mark.asyncio
async def test_bind_start_no_token(client):
    resp = await client.post("/api/config/telegram/bind/start")
    data = resp.json()
    assert data["success"] is False
    assert "Bot Token" in data["error"]


@pytest.mark.asyncio
async def test_bind_start_with_token(client):
    await client.put("/api/config/telegram", json={"bot_token": "fake:token"})
    resp = await client.post("/api/config/telegram/bind/start")
    data = resp.json()
    assert data["success"] is True
    assert len(data["code"]) == 6
    assert data["code"].isdigit()
    # Clean up
    await client.post("/api/config/telegram/bind/cancel")


@pytest.mark.asyncio
async def test_bind_status_idle(client):
    from stake_watch.api.routes.config import _bind_state
    _bind_state.clear()
    resp = await client.get("/api/config/telegram/bind/status")
    data = resp.json()
    assert data["status"] == "idle"


@pytest.mark.asyncio
async def test_bind_cancel(client):
    await client.put("/api/config/telegram", json={"bot_token": "fake:token"})
    await client.post("/api/config/telegram/bind/start")
    resp = await client.post("/api/config/telegram/bind/cancel")
    data = resp.json()
    assert data["status"] == "cancelled"
