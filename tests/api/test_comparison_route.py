"""Tests for the protocol comparison route /api/comparison."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from stake_watch.api.app import create_app
from stake_watch.api.routes.comparison import _liquidity_coeff, _stable_safety_coeff
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage


# ---------- helpers ----------

@pytest.mark.parametrize("tvl,coeff", [
    (5e9, 1.00),
    (5e8, 0.95),
    (2e8, 0.90),
    (5e7, 0.80),
    (2e7, 0.65),
    (1e6, 0.45),
])
def test_liquidity_coeff_tiers(tvl, coeff):
    assert _liquidity_coeff(tvl) == coeff


def test_stable_safety_coeff_known_assets():
    # USDC default risk = 12 → coeff 0.88
    assert _stable_safety_coeff("USDC") == pytest.approx(0.88)
    # USDT default risk = 18 → coeff 0.82
    assert _stable_safety_coeff("USDT") == pytest.approx(0.82)


def test_stable_safety_coeff_unknown_asset_falls_back_to_25():
    assert _stable_safety_coeff("XYZ") == pytest.approx(0.75)


# ---------- route ----------

@pytest.fixture
async def client(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    storage = Storage(db_url)
    await storage.initialize()
    app = create_app(storage)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, storage
    await storage.close()


async def _seed_protocol(storage: Storage, name: str, chain: str,
                          chains_breakdown: list[dict], enabled: bool = True):
    store = ConfigStore(storage._session_factory)
    await store.add_protocol(name=name, chain=chain, collector="defillama",
                              enabled=enabled)
    await store.set_setting(f"protocols.{name}.chains", chains_breakdown)


@pytest.mark.asyncio
async def test_returns_empty_when_no_protocols(client):
    c, _ = client
    r = await c.get("/api/comparison")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["rows"] == []


@pytest.mark.asyncio
async def test_skips_disabled_protocols(client):
    c, storage = client
    await _seed_protocol(storage, "off_proto", "base",
        [{"chain": "BASE", "chain_full": "base",
          "by_asset": {"USDC": {"apy": 5.0, "tvl_usd": 1_000_000}}}],
        enabled=False)
    r = await c.get("/api/comparison")
    assert r.json()["count"] == 0


@pytest.mark.asyncio
async def test_filters_non_target_assets(client):
    c, storage = client
    await _seed_protocol(storage, "proto", "base", [{
        "chain": "BASE", "chain_full": "base", "by_asset": {
            "USDC":  {"apy": 5.0, "tvl_usd": 1_000_000},
            "WETH":  {"apy": 3.0, "tvl_usd": 5_000_000},
        }}])
    r = await c.get("/api/comparison")
    assets = {row["asset"] for row in r.json()["rows"]}
    assert assets == {"USDC"}


@pytest.mark.asyncio
async def test_drops_rows_with_zero_apy_or_tvl(client):
    c, storage = client
    await _seed_protocol(storage, "proto", "base", [{
        "chain": "BASE", "chain_full": "base", "by_asset": {
            "USDC": {"apy": 0, "tvl_usd": 1_000_000},
            "USDT": {"apy": 5.0, "tvl_usd": 0},
        }}])
    r = await c.get("/api/comparison")
    assert r.json()["count"] == 0


@pytest.mark.asyncio
async def test_composite_score_sort_desc(client):
    c, storage = client
    await _seed_protocol(storage, "a", "base", [{
        "chain": "BASE", "chain_full": "base", "by_asset": {
            "USDC": {"apy": 3.0, "tvl_usd": 5_000_000_000}}}])
    await _seed_protocol(storage, "b", "base", [{
        "chain": "BASE", "chain_full": "base", "by_asset": {
            "USDC": {"apy": 8.0, "tvl_usd": 5_000_000_000}}}])
    r = await c.get("/api/comparison")
    rows = r.json()["rows"]
    assert rows[0]["protocol"] == "b"
    assert rows[0]["composite_score"] > rows[1]["composite_score"]


@pytest.mark.asyncio
async def test_peer_median_returned_per_asset(client):
    c, storage = client
    await _seed_protocol(storage, "a", "base", [{
        "chain": "BASE", "chain_full": "base", "by_asset": {
            "USDC": {"apy": 3.0, "tvl_usd": 1_000_000_000}}}])
    await _seed_protocol(storage, "b", "base", [{
        "chain": "BASE", "chain_full": "base", "by_asset": {
            "USDC": {"apy": 5.0, "tvl_usd": 1_000_000_000}}}])
    await _seed_protocol(storage, "c", "base", [{
        "chain": "BASE", "chain_full": "base", "by_asset": {
            "USDC": {"apy": 7.0, "tvl_usd": 1_000_000_000}}}])
    body = (await c.get("/api/comparison")).json()
    assert body["peer_median_apy"]["USDC"] == 5.0


@pytest.mark.asyncio
async def test_apy_premium_signal_flagged(client):
    c, storage = client
    await _seed_protocol(storage, "low", "base", [{
        "chain": "BASE", "chain_full": "base", "by_asset": {
            "USDC": {"apy": 3.0, "tvl_usd": 1_000_000_000}}}])
    await _seed_protocol(storage, "high", "base", [{
        "chain": "BASE", "chain_full": "base", "by_asset": {
            "USDC": {"apy": 9.0, "tvl_usd": 1_000_000_000}}}])
    rows = (await c.get("/api/comparison")).json()["rows"]
    high = [r for r in rows if r["protocol"] == "high"][0]
    assert high["apy_premium_pct"] == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_apy_inverted_flag_when_supply_ge_borrow(client):
    c, storage = client
    await _seed_protocol(storage, "p", "base", [{
        "chain": "BASE", "chain_full": "base", "by_asset": {
            "USDC": {"apy": 6.0, "tvl_usd": 1_000_000, "borrow_apy": 5.0}}}])
    rows = (await c.get("/api/comparison")).json()["rows"]
    assert rows[0]["apy_inverted"] is True


@pytest.mark.asyncio
async def test_live_signals_propagate_to_row(client):
    c, storage = client
    await _seed_protocol(storage, "p", "base", [{
        "chain": "BASE", "chain_full": "base", "by_asset": {
            "USDC": {"apy": 5.0, "tvl_usd": 1_000_000,
                       "utilization": 0.80,
                       "withdrawable_ratio": 0.20,
                       "supply_cap_usage": 0.85}}}])
    row = (await c.get("/api/comparison")).json()["rows"][0]
    assert row["utilization"] == pytest.approx(0.80)
    assert row["withdrawable_ratio"] == pytest.approx(0.20)
    assert row["supply_cap_usage"] == pytest.approx(0.85)
    assert row["has_live_signals"] is True


@pytest.mark.asyncio
async def test_row_has_risk_total_and_level(client):
    c, storage = client
    await _seed_protocol(storage, "aave_v3_base", "base", [{
        "chain": "BASE", "chain_full": "base", "by_asset": {
            "USDC": {"apy": 5.0, "tvl_usd": 5_000_000_000}}}])
    row = (await c.get("/api/comparison")).json()["rows"][0]
    assert 0 <= row["risk_total"] <= 100
    assert row["risk_level"] in {"A", "B", "C", "D", "E"}
    assert row["adjusted_yield_exp"] >= 0
    assert row["adjusted_yield_linear"] >= 0
