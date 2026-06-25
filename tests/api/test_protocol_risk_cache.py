"""Tests for baseline risk_scores persistence + cache-read path."""
from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from stake_watch.api.app import create_app
from stake_watch.api.routes.protocols import (
    _compute_baseline_risk,
    _to_dict,
    recalc_baseline_risk,
)
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage


@pytest.fixture
async def storage(tmp_path):
    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    await s.initialize()
    yield s
    await s.close()


@pytest.fixture
async def store(storage):
    return ConfigStore(storage._session_factory)


@pytest.fixture
async def client(storage):
    app = create_app(storage)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------- _compute_baseline_risk ----------

def test_baseline_shape_for_known_product():
    out = _compute_baseline_risk("aave_v3_base", "base", "USDC")
    assert "total" in out and "level" in out and "dimensions" in out
    assert out["level"] in {"A", "B", "C", "D", "E"}
    assert len(out["dimensions"]) == 8
    assert "evaluated_at" in out


def test_baseline_is_json_serialisable():
    out = _compute_baseline_risk("aave_v3_base", "base", "USDC")
    s = json.dumps(out)
    assert json.loads(s) == out


# ---------- _to_dict cache read ----------

class _FakeRow:
    """Bare-minimum stand-in for a ProtocolConfigRow."""
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_to_dict_uses_cached_risk_when_present():
    cached = _compute_baseline_risk("aave_v3_base", "base", "USDC")
    cached["total"] = 99.9  # sentinel — would never come from evaluate()
    cached["level"] = "E"
    p = _FakeRow(id=1, name="aave_v3_base", chain="base", collector="defillama",
        enabled=True, safety_rank=1, safety_score=8.0, reference_apy=None,
        primary_risks=None, vault_address=None, defillama_slug=None,
        pool_filter=None, protocol_type=None, risk_scores=json.dumps(cached))
    d = _to_dict(p)
    assert d["risk_total"] == 99.9
    assert d["risk_level"] == "E"
    # uses cached dimensions, not freshly computed
    assert d["risk_dimensions"] == cached["dimensions"]


def test_to_dict_falls_back_to_compute_when_cache_missing():
    p = _FakeRow(id=1, name="aave_v3_base", chain="base", collector="defillama",
        enabled=True, safety_rank=1, safety_score=8.0, reference_apy=None,
        primary_risks=None, vault_address=None, defillama_slug=None,
        pool_filter=None, protocol_type=None, risk_scores=None)
    d = _to_dict(p)
    assert d["risk_total"] > 0
    assert d["risk_level"] in {"A", "B", "C", "D", "E"}
    assert len(d["risk_dimensions"]) == 8


def test_to_dict_falls_back_when_cache_is_garbage():
    p = _FakeRow(id=1, name="aave_v3_base", chain="base", collector="defillama",
        enabled=True, safety_rank=1, safety_score=8.0, reference_apy=None,
        primary_risks=None, vault_address=None, defillama_slug=None,
        pool_filter=None, protocol_type=None, risk_scores="not-json")
    d = _to_dict(p)
    assert d["risk_total"] > 0


# ---------- recalc_baseline_risk ----------

@pytest.mark.asyncio
async def test_recalc_populates_risk_scores_for_all_protocols(store):
    for name in ("aave_v3_base", "compound_v3_usdc"):
        await store.add_protocol(name=name, chain="base", collector="defillama")
    # Before recalc — risk_scores empty
    protos = await store.list_protocols()
    assert all(p.risk_scores is None for p in protos)

    n = await recalc_baseline_risk(store)
    assert n == 2

    protos = await store.list_protocols()
    for p in protos:
        assert p.risk_scores is not None
        data = json.loads(p.risk_scores)
        assert "total" in data and "level" in data


# ---------- POST /api/protocols (auto-persists baseline on add) ----------

@pytest.mark.asyncio
async def test_add_protocol_persists_baseline_risk(client, store):
    r = await client.post("/api/protocols", json={
        "name": "aave_v3_base", "chain": "base", "collector": "defillama",
        "enabled": True})
    assert r.status_code == 201
    body = r.json()
    assert body["risk_total"] > 0

    # row in DB has the JSON blob
    protos = await store.list_protocols()
    assert protos[0].risk_scores is not None
    parsed = json.loads(protos[0].risk_scores)
    assert parsed["total"] == body["risk_total"]


# ---------- POST /api/protocols/recalc-risk ----------

@pytest.mark.asyncio
async def test_recalc_endpoint_returns_count(client):
    await client.post("/api/protocols", json={
        "name": "aave_v3_base", "chain": "base", "collector": "defillama"})
    await client.post("/api/protocols", json={
        "name": "compound_v3_usdc", "chain": "base", "collector": "defillama"})
    r = await client.post("/api/protocols/recalc-risk")
    assert r.status_code == 200
    assert r.json() == {"updated": 2}


# ---------- end-to-end: cache hit on GET ----------

@pytest.mark.asyncio
async def test_subsequent_get_uses_cached_risk(client, store, monkeypatch):
    """After add (which persists), GET must NOT call evaluate()."""
    r = await client.post("/api/protocols", json={
        "name": "aave_v3_base", "chain": "base", "collector": "defillama"})
    assert r.status_code == 201

    # Trap any call into evaluate
    calls = {"n": 0}
    import stake_watch.risk.risk_model as rm
    real_evaluate = rm.evaluate

    def tripwire(*args, **kwargs):
        calls["n"] += 1
        return real_evaluate(*args, **kwargs)

    monkeypatch.setattr(rm, "evaluate", tripwire)

    r = await client.get("/api/protocols")
    assert r.status_code == 200
    assert calls["n"] == 0, "GET should use cached risk_scores, not re-evaluate"


@pytest.mark.asyncio
async def test_get_protocols_surfaces_live_risk_when_persisted(client, store):
    """When risk_monitor has persisted a live evaluation, GET /api/protocols
    must include it under `live_risk` so the dashboard can show what
    Telegram alerts see, not just the cached baseline."""
    r = await client.post("/api/protocols", json={
        "name": "compound_v3_usdc", "chain": "base", "collector": "defillama"})
    assert r.status_code == 201
    await store.set_setting("risk_monitor.last_evaluation.compound_v3_usdc", {
        "total": 31.0, "level": "C", "veto_flags": [],
        "primary_chain": "base", "primary_asset": "USDC",
        "evaluated_at": "2026-06-25T08:00:00+00:00",
    })

    body = (await client.get("/api/protocols")).json()
    row = next(x for x in body if x["name"] == "compound_v3_usdc")
    assert row["live_risk"] is not None
    assert row["live_risk"]["total"] == 31.0
    assert row["live_risk"]["level"] == "C"
    # baseline still exposed for comparison
    assert row["risk_total_baseline"] is not None


@pytest.mark.asyncio
async def test_get_protocols_live_risk_absent_when_no_monitor_run(client, store):
    await client.post("/api/protocols", json={
        "name": "aave_v3_base", "chain": "base", "collector": "defillama"})
    body = (await client.get("/api/protocols")).json()
    assert body[0]["live_risk"] is None
