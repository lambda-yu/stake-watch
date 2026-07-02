"""Tests for Morpho GraphQL historicalState fetcher + route priority."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stake_watch.collectors.morpho.morpho_history import fetch_vault_history


def _patch_post(payload):
    client = MagicMock()
    resp = MagicMock()
    resp.json = MagicMock(return_value=payload)
    resp.raise_for_status = MagicMock()
    client.post = AsyncMock(return_value=resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("httpx.AsyncClient", return_value=ctx)


# ---------- fetch_vault_history ----------

@pytest.mark.asyncio
async def test_parses_dailyapys_and_tvl_merge_by_timestamp():
    now = int(datetime.now(timezone.utc).timestamp())
    payload = {"data": {"vaultByAddress": {"historicalState": {
        "dailyApys": [
            {"x": now - 86400 * 2, "y": 0.048},   # 4.8%
            {"x": now - 86400,     "y": 0.052},   # 5.2%
        ],
        "totalAssetsUsd": [
            {"x": now - 86400 * 2, "y": 1_000_000},
            {"x": now - 86400,     "y": 1_200_000},
        ],
    }}}}
    with _patch_post(payload):
        points = await fetch_vault_history("0xBEEF", "base", days=7)
    assert len(points) == 2
    # APY is normalized to percentage
    assert points[0]["apy"] == pytest.approx(4.8)
    assert points[1]["apy"] == pytest.approx(5.2)
    # TVL merged by matching timestamp
    assert points[0]["tvl_usd"] == 1_000_000
    assert points[1]["tvl_usd"] == 1_200_000
    # Sorted ascending
    assert points[0]["t"] < points[1]["t"]


@pytest.mark.asyncio
async def test_empty_when_vault_not_found():
    with _patch_post({"data": {"vaultByAddress": None}}):
        points = await fetch_vault_history("0xNONE", "base", days=30)
    assert points == []


@pytest.mark.asyncio
async def test_empty_when_no_history():
    payload = {"data": {"vaultByAddress": {"historicalState": {
        "dailyApys": [], "totalAssetsUsd": []}}}}
    with _patch_post(payload):
        points = await fetch_vault_history("0xBEEF", "base", days=30)
    assert points == []


@pytest.mark.asyncio
async def test_empty_on_upstream_error():
    client = MagicMock()
    client.post = AsyncMock(side_effect=Exception("boom"))
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)
    with patch("httpx.AsyncClient", return_value=ctx):
        points = await fetch_vault_history("0xBEEF", "base", days=30)
    assert points == []


@pytest.mark.asyncio
async def test_skips_malformed_apy_points():
    now = int(datetime.now(timezone.utc).timestamp())
    payload = {"data": {"vaultByAddress": {"historicalState": {
        "dailyApys": [
            {"x": now, "y": None},               # bad — skip
            {"x": "not-a-ts", "y": 0.05},        # bad ts — skip
            {"x": now - 3600, "y": 0.06},        # good
        ],
        "totalAssetsUsd": [],
    }}}}
    with _patch_post(payload):
        points = await fetch_vault_history("0xBEEF", "base", days=7)
    assert len(points) == 1
    assert points[0]["apy"] == pytest.approx(6.0)


# ---------- route priority: Morpho > DefiLlama > snapshots ----------

@pytest.mark.asyncio
async def test_route_prefers_morpho_over_defillama_for_morpho_vaults(tmp_path):
    from httpx import ASGITransport, AsyncClient
    from stake_watch.api.app import create_app
    from stake_watch.storage.db import Storage

    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await s.initialize()
    app = create_app(s)
    async with AsyncClient(transport=ASGITransport(app=app),
                             base_url="http://test") as c:
        r = await c.post("/api/protocols", json={
            "name": "morpho_steakhouse_usdc", "chain": "base",
            "collector": "morpho", "defillama_slug": "morpho-blue",
            "vault_address": "0xBEEF", "pool_filter": "STEAKUSDC"})
        pid = r.json()["id"]

        now = int(datetime.now(timezone.utc).timestamp())
        morpho_payload = {"data": {"vaultByAddress": {"historicalState": {
            "dailyApys": [{"x": now - 3600, "y": 0.077}],
            "totalAssetsUsd": [{"x": now - 3600, "y": 5_000_000}],
        }}}}

        # Morpho path should short-circuit — DefiLlama shouldn't even be hit.
        # We DON'T mock DefiLlama; if it were called it would hit the network
        # in tests (or fail). Route should never reach it.
        with _patch_post(morpho_payload):
            body = (await c.get(f"/api/protocols/{pid}/history?days=7")).json()

        assert body["source"] == "morpho"
        assert body["count"] == 1
        assert body["series"][0]["points"][0]["apy"] == pytest.approx(7.7)
    await s.close()


@pytest.mark.asyncio
async def test_route_falls_back_to_defillama_when_morpho_history_empty(tmp_path):
    from httpx import ASGITransport, AsyncClient
    from stake_watch.api.app import create_app
    from stake_watch.storage.db import Storage
    from stake_watch.collectors import defillama_history as dl_mod

    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await s.initialize()
    app = create_app(s)
    async with AsyncClient(transport=ASGITransport(app=app),
                             base_url="http://test") as c:
        r = await c.post("/api/protocols", json={
            "name": "morpho_steakhouse_usdc", "chain": "base",
            "collector": "morpho", "defillama_slug": "morpho-blue",
            "vault_address": "0xEMPTY"})
        pid = r.json()["id"]

        # Morpho returns nothing → we must fall back to DefiLlama
        empty_morpho = {"data": {"vaultByAddress": None}}
        dl_stub = AsyncMock(return_value=[
            {"t": "2026-06-01T00:00:00+00:00", "apy": 5.3, "tvl_usd": 1},
        ])
        with _patch_post(empty_morpho), \
             patch.object(dl_mod, "fetch_protocol_history", dl_stub):
            body = (await c.get(f"/api/protocols/{pid}/history?days=7")).json()

        assert body["source"] == "defillama"
        assert body["count"] == 1
    await s.close()
