"""Tests for the DefiLlama historical APY/TVL fetcher."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stake_watch.collectors.defillama_history import (
    fetch_pool_chart,
    fetch_protocol_history,
    resolve_pool_id,
)
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage


def _patch_get(json_by_url: dict):
    """Patch httpx.AsyncClient so .get(url) dispatches by URL prefix."""
    async def fake_get(url, *args, **kwargs):
        for key, body in json_by_url.items():
            if key in url:
                resp = MagicMock()
                resp.json = MagicMock(return_value=body)
                resp.raise_for_status = MagicMock()
                return resp
        raise RuntimeError(f"Unexpected URL {url}")
    client = MagicMock()
    client.get = AsyncMock(side_effect=fake_get)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("httpx.AsyncClient", return_value=ctx)


# ---------- resolve_pool_id ----------

@pytest.mark.asyncio
async def test_resolve_matches_by_slug_chain_asset():
    payload = {"data": [
        {"project": "aave-v3", "chain": "Ethereum", "symbol": "USDC",
         "pool": "aave-eth-usdc"},
        {"project": "aave-v3", "chain": "Base", "symbol": "USDC",
         "pool": "aave-base-usdc"},
    ]}
    with _patch_get({"/pools": payload}):
        pid = await resolve_pool_id("aave-v3", "base", "USDC")
    assert pid == "aave-base-usdc"


@pytest.mark.asyncio
async def test_resolve_uses_pool_filter_for_morpho_style_vaults():
    payload = {"data": [
        {"project": "morpho-blue", "chain": "Base", "symbol": "STEAKUSDC",
         "pool": "morpho-steakhouse"},
        {"project": "morpho-blue", "chain": "Base", "symbol": "GTUSDCP",
         "pool": "morpho-gauntlet"},
    ]}
    with _patch_get({"/pools": payload}):
        pid = await resolve_pool_id("morpho-blue", "base", "USDC",
                                       pool_filter="GTUSDCP")
    assert pid == "morpho-gauntlet"


@pytest.mark.asyncio
async def test_resolve_returns_none_on_no_match():
    with _patch_get({"/pools": {"data": []}}):
        pid = await resolve_pool_id("nope", "ethereum", "USDC")
    assert pid is None


@pytest.mark.asyncio
async def test_resolve_returns_none_on_upstream_failure():
    from unittest.mock import AsyncMock, MagicMock, patch as p
    client = MagicMock()
    client.get = AsyncMock(side_effect=Exception("net down"))
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)
    with p("httpx.AsyncClient", return_value=ctx):
        pid = await resolve_pool_id("aave-v3", "base", "USDC")
    assert pid is None


# ---------- fetch_pool_chart ----------

@pytest.mark.asyncio
async def test_chart_filters_older_than_days_and_sorts_ascending():
    now = datetime.now(timezone.utc)
    payload = {"data": [
        {"timestamp": (now - timedelta(days=45)).isoformat().replace("+00:00", "Z"),
         "apy": 4.0, "tvlUsd": 1_000_000},
        {"timestamp": (now - timedelta(days=3)).isoformat().replace("+00:00", "Z"),
         "apy": 5.5, "tvlUsd": 1_200_000},
        {"timestamp": (now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
         "apy": 5.8, "tvlUsd": 1_300_000},
    ]}
    with _patch_get({"/chart/pool-abc": payload}):
        points = await fetch_pool_chart("pool-abc", days=7)
    assert [p["apy"] for p in points] == [5.5, 5.8]  # older filtered, sorted asc


@pytest.mark.asyncio
async def test_chart_empty_on_upstream_error():
    from unittest.mock import AsyncMock, MagicMock, patch as p
    client = MagicMock()
    client.get = AsyncMock(side_effect=Exception("boom"))
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)
    with p("httpx.AsyncClient", return_value=ctx):
        points = await fetch_pool_chart("pool", days=7)
    assert points == []


@pytest.mark.asyncio
async def test_chart_skips_malformed_points():
    now = datetime.now(timezone.utc)
    payload = {"data": [
        {"timestamp": (now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
         "apy": None, "tvlUsd": 1},  # apy missing → skip
        {"timestamp": "not-a-date", "apy": 5.0, "tvlUsd": 1},  # bad ts → skip
        {"timestamp": (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
         "apy": 5.0, "tvlUsd": 1},  # good
    ]}
    with _patch_get({"/chart/pool": payload}):
        points = await fetch_pool_chart("pool", days=7)
    assert len(points) == 1
    assert points[0]["apy"] == 5.0


# ---------- fetch_protocol_history + caching ----------

@pytest.fixture
async def env(tmp_path):
    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await s.initialize()
    yield ConfigStore(s._session_factory), s
    await s.close()


@pytest.mark.asyncio
async def test_fetch_protocol_history_caches_pool_id(env):
    store, _ = env
    now = datetime.now(timezone.utc)
    pools_payload = {"data": [
        {"project": "aave-v3", "chain": "Base", "symbol": "USDC",
         "pool": "aave-base-usdc"},
    ]}
    chart_payload = {"data": [
        {"timestamp": (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
         "apy": 5.0, "tvlUsd": 1},
    ]}
    with _patch_get({"/pools": pools_payload, "/chart/": chart_payload}):
        pts = await fetch_protocol_history(
            store, protocol_name="aave_v3_base", slug="aave-v3",
            chain="base", asset="USDC", pool_filter=None, days=7)
    assert len(pts) == 1
    cached = await store.get_setting("history.pool_id.aave_v3_base.base.USDC")
    assert cached == "aave-base-usdc"


@pytest.mark.asyncio
async def test_fetch_protocol_history_uses_cache_on_second_call(env):
    store, _ = env
    now = datetime.now(timezone.utc)
    chart_payload = {"data": [
        {"timestamp": now.isoformat().replace("+00:00", "Z"),
         "apy": 4.2, "tvlUsd": 1},
    ]}
    # Pre-seed cache
    await store.set_setting("history.pool_id.p.base.USDC", "cached-pool-id")

    # Only /chart/ should be hit — no /pools call
    with _patch_get({"/chart/cached-pool-id": chart_payload}):
        pts = await fetch_protocol_history(
            store, protocol_name="p", slug="whatever", chain="base",
            asset="USDC", pool_filter=None, days=7)
    assert len(pts) == 1
    assert pts[0]["apy"] == 4.2


@pytest.mark.asyncio
async def test_fetch_protocol_history_empty_when_no_pool_match(env):
    store, _ = env
    with _patch_get({"/pools": {"data": []}}):
        pts = await fetch_protocol_history(
            store, protocol_name="p", slug="mystery", chain="base",
            asset="USDC", pool_filter=None, days=7)
    assert pts == []


# ---------- route integration ----------

@pytest.mark.asyncio
async def test_route_prefers_defillama_over_local_snapshots(tmp_path):
    """When source=auto and DefiLlama returns data, snapshots are ignored."""
    from httpx import ASGITransport, AsyncClient
    from stake_watch.api.app import create_app
    from stake_watch.storage.tables import TvlSnapshotRow

    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/api.db")
    await s.initialize()
    app = create_app(s)
    async with AsyncClient(transport=ASGITransport(app=app),
                             base_url="http://test") as c:
        r = await c.post("/api/protocols", json={
            "name": "aave_v3_base", "chain": "base", "collector": "defillama",
            "defillama_slug": "aave-v3"})
        pid = r.json()["id"]

        # Add a local snapshot so we can tell it wasn't used
        async with s._session_factory() as session:
            session.add(TvlSnapshotRow(protocol="aave_v3_base", chain="base",
                                         asset="USDC", apy=99.9, tvl_usd=1,
                                         created_at=datetime.now(timezone.utc)))
            await session.commit()

        now = datetime.now(timezone.utc)
        pools = {"data": [
            {"project": "aave-v3", "chain": "Base", "symbol": "USDC",
             "pool": "aave-usdc-pool"}]}
        chart = {"data": [
            {"timestamp": (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
             "apy": 5.5, "tvlUsd": 1}]}
        with _patch_get({"/pools": pools, "/chart/": chart}):
            body = (await c.get(f"/api/protocols/{pid}/history?days=7")).json()
        assert body["source"] == "defillama"
        assert body["count"] == 1
        # Should be 5.5 from DefiLlama, not 99.9 from local snapshots
        assert body["series"][0]["points"][0]["apy"] == 5.5
    await s.close()


@pytest.mark.asyncio
async def test_route_falls_back_to_snapshots_when_defillama_returns_nothing(tmp_path):
    from httpx import ASGITransport, AsyncClient
    from stake_watch.api.app import create_app
    from stake_watch.storage.tables import TvlSnapshotRow

    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/api.db")
    await s.initialize()
    app = create_app(s)
    async with AsyncClient(transport=ASGITransport(app=app),
                             base_url="http://test") as c:
        r = await c.post("/api/protocols", json={
            "name": "p", "chain": "base", "collector": "defillama",
            "defillama_slug": "no-such-slug"})
        pid = r.json()["id"]
        async with s._session_factory() as session:
            session.add(TvlSnapshotRow(protocol="p", chain="base",
                                         asset="USDC", apy=7.0, tvl_usd=1,
                                         created_at=datetime.now(timezone.utc)))
            await session.commit()
        with _patch_get({"/pools": {"data": []}}):
            body = (await c.get(f"/api/protocols/{pid}/history?days=7")).json()
        assert body["source"] == "snapshots"
        assert body["series"][0]["points"][0]["apy"] == 7.0
    await s.close()


@pytest.mark.asyncio
async def test_route_source_official_returns_empty_when_unavailable(tmp_path):
    from httpx import ASGITransport, AsyncClient
    from stake_watch.api.app import create_app
    from stake_watch.storage.tables import TvlSnapshotRow

    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/api.db")
    await s.initialize()
    app = create_app(s)
    async with AsyncClient(transport=ASGITransport(app=app),
                             base_url="http://test") as c:
        r = await c.post("/api/protocols", json={
            "name": "p", "chain": "base", "collector": "defillama",
            "defillama_slug": "no-such-slug"})
        pid = r.json()["id"]
        # Local snapshots exist but source=official should ignore them
        async with s._session_factory() as session:
            session.add(TvlSnapshotRow(protocol="p", chain="base",
                                         asset="USDC", apy=7.0, tvl_usd=1,
                                         created_at=datetime.now(timezone.utc)))
            await session.commit()
        with _patch_get({"/pools": {"data": []}}):
            body = (await c.get(f"/api/protocols/{pid}/history?days=7&source=official")).json()
        assert body["source"] == "empty"
        assert body["count"] == 0
    await s.close()
