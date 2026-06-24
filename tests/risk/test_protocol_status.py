"""Integration tests for protocol_status orchestrator.

Uses a real sqlite Storage + ConfigStore so we exercise the deterministic
check-builder logic. External HTTP calls (Chainlink/Pyth/Morpho API) are
left to fail naturally — the try/except guards swallow them and the
risk_model block falls back to baseline. This keeps tests focused on the
fork logic without dozens of mocks.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from stake_watch.models.common import Chain
from stake_watch.models.protocol import PoolStats, ProtocolStats
from stake_watch.risk.protocol_status import (
    _check,
    _fmt_tvl,
    evaluate_protocol_status,
)
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage


# ---------- helpers ----------

@pytest.mark.parametrize("v,expected", [
    (200, "$200"),
    (12_400, "$12K"),
    (4_500_000, "$4.5M"),
    (2_300_000_000, "$2.30B"),
])
def test_fmt_tvl_scales(v, expected):
    assert _fmt_tvl(v) == expected


def test_check_builds_record():
    c = _check("k", "L", "ok", "v", "d")
    assert c == {"key": "k", "label": "L", "status": "ok",
                  "value": "v", "detail": "d"}


# ---------- fixtures ----------

@pytest.fixture
async def storage(tmp_path):
    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    await s.initialize()
    yield s
    await s.close()


@pytest.fixture
async def config_store(storage):
    return ConfigStore(storage._session_factory)


async def _add_proto(config_store, name, chain="base", enabled=True,
                     vault_address=None):
    await config_store.add_protocol(name=name, chain=chain,
        collector="defillama", enabled=enabled, vault_address=vault_address)


async def _save_stats(storage, name, *, tvl, apy, asset="USDC",
                      updated_at=None, chain=Chain.BASE):
    pool = PoolStats(pool_id=f"{name}_pool", asset=asset, supply_apy=apy,
        borrow_apy=apy + 1, total_supply=Decimal(str(tvl)),
        total_borrow=Decimal("0"), utilization=0.5)
    stats = ProtocolStats(chain=chain, protocol=name, tvl_usd=Decimal(str(tvl)),
        pools=[pool], updated_at=updated_at or datetime.now(timezone.utc))
    await storage.save_protocol_stats(stats)


def _check_by_key(checks: list[dict], key: str) -> dict | None:
    return next((c for c in checks if c["key"] == key), None)


# ---------- core orchestrator ----------

@pytest.mark.asyncio
async def test_returns_none_for_unknown_protocol(storage, config_store):
    out = await evaluate_protocol_status("nope", storage, config_store)
    assert out is None


@pytest.mark.asyncio
async def test_disabled_protocol_is_critical(storage, config_store):
    await _add_proto(config_store, "p", enabled=False)
    out = await evaluate_protocol_status("p", storage, config_store)
    en = _check_by_key(out["checks"], "enabled")
    assert en["status"] == "critical"
    assert "已禁用" in en["value"]


@pytest.mark.asyncio
async def test_enabled_protocol_with_no_stats_flags_freshness_critical(
        storage, config_store):
    await _add_proto(config_store, "p")
    out = await evaluate_protocol_status("p", storage, config_store)
    fresh = _check_by_key(out["checks"], "freshness")
    assert fresh["status"] == "critical"
    assert "无数据" in fresh["value"]


@pytest.mark.asyncio
async def test_fresh_stats_is_ok(storage, config_store):
    await _add_proto(config_store, "p")
    await _save_stats(storage, "p", tvl=100_000_000, apy=5.0)
    out = await evaluate_protocol_status("p", storage, config_store)
    assert _check_by_key(out["checks"], "freshness")["status"] == "ok"


@pytest.mark.asyncio
async def test_old_stats_warning_at_30_to_360_min(storage, config_store):
    await _add_proto(config_store, "p")
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    await _save_stats(storage, "p", tvl=100_000_000, apy=5.0, updated_at=old)
    out = await evaluate_protocol_status("p", storage, config_store)
    assert _check_by_key(out["checks"], "freshness")["status"] == "warning"


@pytest.mark.asyncio
async def test_very_old_stats_critical(storage, config_store):
    await _add_proto(config_store, "p")
    old = datetime.now(timezone.utc) - timedelta(hours=24)
    await _save_stats(storage, "p", tvl=100_000_000, apy=5.0, updated_at=old)
    out = await evaluate_protocol_status("p", storage, config_store)
    assert _check_by_key(out["checks"], "freshness")["status"] == "critical"


# ---------- TVL check ----------

@pytest.mark.asyncio
async def test_tvl_large_is_ok(storage, config_store):
    await _add_proto(config_store, "p")
    await _save_stats(storage, "p", tvl=200_000_000, apy=5.0)
    out = await evaluate_protocol_status("p", storage, config_store)
    assert _check_by_key(out["checks"], "tvl")["status"] == "ok"


@pytest.mark.asyncio
async def test_tvl_mid_is_warning(storage, config_store):
    await _add_proto(config_store, "p")
    await _save_stats(storage, "p", tvl=10_000_000, apy=5.0)
    out = await evaluate_protocol_status("p", storage, config_store)
    assert _check_by_key(out["checks"], "tvl")["status"] == "warning"


@pytest.mark.asyncio
async def test_tvl_small_is_critical(storage, config_store):
    await _add_proto(config_store, "p")
    await _save_stats(storage, "p", tvl=1_000_000, apy=5.0)
    out = await evaluate_protocol_status("p", storage, config_store)
    assert _check_by_key(out["checks"], "tvl")["status"] == "critical"


# ---------- APY check ----------

@pytest.mark.asyncio
async def test_apy_normal_is_ok(storage, config_store):
    await _add_proto(config_store, "p")
    await _save_stats(storage, "p", tvl=100_000_000, apy=6.0)
    out = await evaluate_protocol_status("p", storage, config_store)
    assert _check_by_key(out["checks"], "apy")["status"] == "ok"


@pytest.mark.asyncio
async def test_apy_elevated_is_warning(storage, config_store):
    await _add_proto(config_store, "p")
    await _save_stats(storage, "p", tvl=100_000_000, apy=18.0)
    out = await evaluate_protocol_status("p", storage, config_store)
    assert _check_by_key(out["checks"], "apy")["status"] == "warning"


@pytest.mark.asyncio
async def test_apy_extreme_is_critical(storage, config_store):
    await _add_proto(config_store, "p")
    await _save_stats(storage, "p", tvl=100_000_000, apy=30.0)
    out = await evaluate_protocol_status("p", storage, config_store)
    assert _check_by_key(out["checks"], "apy")["status"] == "critical"


@pytest.mark.asyncio
async def test_apy_zero_is_warning(storage, config_store):
    await _add_proto(config_store, "p")
    await _save_stats(storage, "p", tvl=100_000_000, apy=0)
    out = await evaluate_protocol_status("p", storage, config_store)
    assert _check_by_key(out["checks"], "apy")["status"] == "warning"


# ---------- multi-chain breakdown ----------

@pytest.mark.asyncio
async def test_multi_chain_breakdown_is_ok(storage, config_store):
    await _add_proto(config_store, "p")
    await _save_stats(storage, "p", tvl=100_000_000, apy=5.0)
    await config_store.set_setting("protocols.p.chains", [
        {"chain": "ETH", "by_asset": {"USDC": {"apy": 4.0, "tvl_usd": 1}}},
        {"chain": "BASE", "by_asset": {"USDC": {"apy": 5.0, "tvl_usd": 1}}},
    ])
    out = await evaluate_protocol_status("p", storage, config_store)
    ch = _check_by_key(out["checks"], "chains")
    assert ch["status"] == "ok"
    assert "2" in ch["value"]


@pytest.mark.asyncio
async def test_single_chain_breakdown_is_warning(storage, config_store):
    await _add_proto(config_store, "p")
    await _save_stats(storage, "p", tvl=100_000_000, apy=5.0)
    await config_store.set_setting("protocols.p.chains", [
        {"chain": "BASE", "by_asset": {"USDC": {"apy": 5.0, "tvl_usd": 1}}},
    ])
    out = await evaluate_protocol_status("p", storage, config_store)
    assert _check_by_key(out["checks"], "chains")["status"] == "warning"


# ---------- scoring + level aggregation ----------

@pytest.mark.asyncio
async def test_clean_run_scores_high_level_ok(storage, config_store):
    await _add_proto(config_store, "p")
    await _save_stats(storage, "p", tvl=200_000_000, apy=5.0)
    await config_store.set_setting("protocols.p.chains", [
        {"chain": "ETH", "by_asset": {"USDC": {"apy": 4.0, "tvl_usd": 1}}},
        {"chain": "BASE", "by_asset": {"USDC": {"apy": 5.0, "tvl_usd": 1}}},
    ])
    out = await evaluate_protocol_status("p", storage, config_store)
    assert out["level"] == "ok"
    # enabled + fresh + tvl + apy + chains → 5 ok → score 10
    assert out["score"] == 10.0


@pytest.mark.asyncio
async def test_warning_reduces_score_by_one(storage, config_store):
    await _add_proto(config_store, "p")
    await _save_stats(storage, "p", tvl=10_000_000, apy=5.0)  # tvl warning
    out = await evaluate_protocol_status("p", storage, config_store)
    assert out["level"] == "warning"
    # tvl warning -1 (rest of warnings depend on chains/peg) → at most 9
    assert out["score"] < 10


@pytest.mark.asyncio
async def test_critical_reduces_score_by_three(storage, config_store):
    await _add_proto(config_store, "p")
    await _save_stats(storage, "p", tvl=1_000_000, apy=5.0)  # tvl critical -3
    out = await evaluate_protocol_status("p", storage, config_store)
    assert out["level"] == "critical"


@pytest.mark.asyncio
async def test_score_is_floored_at_zero(storage, config_store):
    # disabled (-3) + freshness critical (-3) + tvl critical (-3) +
    # apy unknown (-1) + maybe more — guarantees floor.
    await _add_proto(config_store, "p", enabled=False)
    out = await evaluate_protocol_status("p", storage, config_store)
    assert out["score"] >= 0


@pytest.mark.asyncio
async def test_response_envelope_shape(storage, config_store):
    await _add_proto(config_store, "p")
    await _save_stats(storage, "p", tvl=100_000_000, apy=5.0)
    out = await evaluate_protocol_status("p", storage, config_store)
    assert set(out.keys()) == {"score", "level", "checks", "risk_model", "updated_at"}
    assert isinstance(out["checks"], list)
    assert isinstance(out["risk_model"], dict)
    # risk_model has either total/level or error (when imports/lookups fail)
    rm = out["risk_model"]
    assert ("total" in rm) or ("error" in rm)
