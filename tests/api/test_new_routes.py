"""Tests for /api/status, /api/positions, /api/backup."""
from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from stake_watch.api.app import create_app
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage


@pytest.fixture
async def app_client(tmp_path):
    db_path = tmp_path / "test.db"
    storage = Storage(f"sqlite+aiosqlite:///{db_path}")
    await storage.initialize()
    store = ConfigStore(storage._session_factory)
    app = create_app(storage)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, storage, store, db_path
    await storage.close()


# ---------- /api/status ----------

@pytest.mark.asyncio
async def test_status_includes_protocol_counts(app_client):
    c, _, store, _ = app_client
    await store.add_protocol(name="a", chain="base", collector="defillama", enabled=True)
    await store.add_protocol(name="b", chain="base", collector="defillama", enabled=False)
    body = (await c.get("/api/status")).json()
    assert body["status"] == "running"
    assert body["protocols"] == {"total": 2, "enabled": 1}
    assert "now" in body
    assert "data" in body and "alerts" in body


@pytest.mark.asyncio
async def test_status_alert_age_when_alert_exists(app_client):
    from datetime import datetime, timezone
    from stake_watch.models.alert import Alert, RuleType, Severity
    c, storage, _, _ = app_client
    await storage.save_alert(Alert(rule_type=RuleType.PROTOCOL_EVENT,
        severity=Severity.WARNING, protocol="x", chain="base",
        title="t", message="m", created_at=datetime.now(timezone.utc)))
    body = (await c.get("/api/status")).json()
    assert body["alerts"]["last_alert_at"] is not None
    assert body["alerts"]["last_alert_age_seconds"] is not None


# ---------- /api/positions ----------

@pytest.mark.asyncio
async def test_positions_returns_empty_for_unconfigured(app_client):
    c, _, _, _ = app_client
    body = (await c.get("/api/positions")).json()
    assert body == {"positions": [], "count": 0}


@pytest.mark.asyncio
async def test_positions_filtered_by_wallet_query(app_client):
    from datetime import datetime, timezone
    from decimal import Decimal
    from stake_watch.models.common import Chain, PositionType
    from stake_watch.models.position import Position
    c, storage, _, _ = app_client
    pos = Position(chain=Chain.BASE, protocol="aave_v3_base", wallet="0xW",
        asset="USDC", position_type=PositionType.SUPPLY,
        amount=Decimal("1000"), value_usd=Decimal("1000"),
        apy=5.0, ltv=None, health_factor=None, vault_version=None,
        updated_at=datetime.now(timezone.utc))
    await storage.save_positions([pos])
    body = (await c.get("/api/positions?wallet=0xW")).json()
    assert body["count"] == 1
    assert body["positions"][0]["asset"] == "USDC"
    assert body["positions"][0]["apy"] == 5.0


# ---------- /api/backup ----------

@pytest.mark.asyncio
async def test_backup_sqlite_returns_file_contents(app_client):
    c, _, _, db_path = app_client
    r = await c.get("/api/backup/sqlite")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    assert "attachment" in r.headers["content-disposition"]
    # SQLite files start with this magic string
    assert r.content[:15] == b"SQLite format 3"


@pytest.mark.asyncio
async def test_backup_json_includes_core_sections(app_client):
    c, _, store, _ = app_client
    await store.add_protocol(name="p", chain="base", collector="defillama")
    await store.add_wallet("ethereum", "0xWALLET", label="primary")
    r = await c.get("/api/backup/json")
    assert r.status_code == 200
    body = json.loads(r.content)
    assert "exported_at" in body
    assert any(x["name"] == "p" for x in body["protocols"])
    assert any(x["address"] == "0xWALLET" for x in body["wallets"])
    # Required sections all present
    for k in ("settings", "alerts", "tvl_snapshots", "vault_share_prices",
               "positions", "rpcs", "latest_protocol_stats"):
        assert k in body
