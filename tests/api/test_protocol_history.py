"""Tests for GET /api/protocols/{id}/history — APY / TVL timeseries."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from stake_watch.api.app import create_app
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage
from stake_watch.storage.tables import TvlSnapshotRow


@pytest.fixture
async def env(tmp_path):
    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await s.initialize()
    store = ConfigStore(s._session_factory)
    app = create_app(s)
    async with AsyncClient(transport=ASGITransport(app=app),
                             base_url="http://test") as c:
        yield c, s, store
    await s.close()


async def _insert_snapshot(storage: Storage, *, protocol: str, chain: str,
                            asset: str, apy: float, tvl: float,
                            created_at: datetime):
    async with storage._session_factory() as session:
        session.add(TvlSnapshotRow(protocol=protocol, chain=chain, asset=asset,
                                     apy=apy, tvl_usd=tvl,
                                     created_at=created_at))
        await session.commit()


@pytest.mark.asyncio
async def test_history_empty_series_when_no_snapshots(env):
    c, _, store = env
    r = await c.post("/api/protocols", json={
        "name": "p", "chain": "base", "collector": "defillama"})
    pid = r.json()["id"]
    r = await c.get(f"/api/protocols/{pid}/history?days=7")
    body = r.json()
    assert body["protocol"] == "p"
    assert body["days"] == 7
    assert body["series"] == []
    assert body["count"] == 0


@pytest.mark.asyncio
async def test_history_groups_by_chain_and_asset(env):
    c, s, store = env
    r = await c.post("/api/protocols", json={
        "name": "aave_v3_base", "chain": "base", "collector": "defillama"})
    pid = r.json()["id"]
    now = datetime.now(timezone.utc)
    await _insert_snapshot(s, protocol="aave_v3_base", chain="base",
                             asset="USDC", apy=5.1, tvl=1_000_000,
                             created_at=now - timedelta(days=2))
    await _insert_snapshot(s, protocol="aave_v3_base", chain="base",
                             asset="USDC", apy=5.4, tvl=1_100_000,
                             created_at=now - timedelta(days=1))
    await _insert_snapshot(s, protocol="aave_v3_base", chain="ethereum",
                             asset="USDT", apy=6.0, tvl=500_000,
                             created_at=now - timedelta(days=1))
    body = (await c.get(f"/api/protocols/{pid}/history?days=7")).json()
    assert body["count"] == 3
    keys = {(x["chain"], x["asset"]) for x in body["series"]}
    assert keys == {("base", "USDC"), ("ethereum", "USDT")}
    base_usdc = next(x for x in body["series"]
                      if x["chain"] == "base" and x["asset"] == "USDC")
    assert len(base_usdc["points"]) == 2


@pytest.mark.asyncio
async def test_history_excludes_older_than_days(env):
    c, s, _ = env
    r = await c.post("/api/protocols", json={
        "name": "p", "chain": "base", "collector": "defillama"})
    pid = r.json()["id"]
    now = datetime.now(timezone.utc)
    await _insert_snapshot(s, protocol="p", chain="base", asset="USDC",
                             apy=5.0, tvl=1, created_at=now - timedelta(days=45))
    await _insert_snapshot(s, protocol="p", chain="base", asset="USDC",
                             apy=6.0, tvl=1, created_at=now - timedelta(days=2))
    body = (await c.get(f"/api/protocols/{pid}/history?days=7")).json()
    assert body["count"] == 1
    assert body["series"][0]["points"][0]["apy"] == 6.0


@pytest.mark.asyncio
async def test_history_points_sorted_ascending(env):
    c, s, _ = env
    r = await c.post("/api/protocols", json={
        "name": "p", "chain": "base", "collector": "defillama"})
    pid = r.json()["id"]
    now = datetime.now(timezone.utc)
    # Insert out of order
    await _insert_snapshot(s, protocol="p", chain="base", asset="USDC",
                             apy=6.0, tvl=1, created_at=now - timedelta(days=1))
    await _insert_snapshot(s, protocol="p", chain="base", asset="USDC",
                             apy=5.0, tvl=1, created_at=now - timedelta(days=3))
    await _insert_snapshot(s, protocol="p", chain="base", asset="USDC",
                             apy=5.5, tvl=1, created_at=now - timedelta(days=2))
    body = (await c.get(f"/api/protocols/{pid}/history?days=7")).json()
    apys = [p["apy"] for p in body["series"][0]["points"]]
    assert apys == [5.0, 5.5, 6.0]


@pytest.mark.asyncio
async def test_history_days_clamped_to_1_365(env):
    c, _, _ = env
    r = await c.post("/api/protocols", json={
        "name": "p", "chain": "base", "collector": "defillama"})
    pid = r.json()["id"]
    r = await c.get(f"/api/protocols/{pid}/history?days=9999")
    assert r.json()["days"] == 365
    r = await c.get(f"/api/protocols/{pid}/history?days=0")
    assert r.json()["days"] == 1


@pytest.mark.asyncio
async def test_history_returns_404_for_unknown(env):
    c, _, _ = env
    r = await c.get("/api/protocols/9999/history")
    assert r.status_code == 404
