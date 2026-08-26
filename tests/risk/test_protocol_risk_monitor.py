"""Tests for the periodic risk monitor that emits veto/level alerts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from stake_watch.models.alert import Alert, RuleType, Severity
from stake_watch.risk.protocol_risk_monitor import (
    _escalation_reason,
    _is_escalation,
    run_risk_monitor,
)
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage


# ---------- _is_escalation ----------

@pytest.mark.parametrize("old,new,expected", [
    ("A", "B", True),  ("A", "E", True),  ("D", "E", True),
    ("B", "A", False), ("C", "C", False),
    (None, "B", False),    # first observation never escalates
    ("Z", "E", False),     # unknown old → noop
])
def test_is_escalation(old, new, expected):
    assert _is_escalation(old, new) is expected


# ---------- _escalation_reason ----------

NO_HISTORY_TEXT = "（无历史维度数据，无法定位具体原因）"


def test_escalation_reason_picks_max_positive_delta():
    old_dims = {"contract": 10, "market": 18, "liquidity": 12}
    new_dims = [
        {"key": "contract", "label": "协议与合约", "score": 10, "notes": ""},
        {"key": "market", "label": "市场与坏账", "score": 50,
         "notes": "坏账率 0.30%，需关注"},
        {"key": "liquidity", "label": "提现流动性", "score": 20, "notes": ""},
    ]
    reason_line, detail = _escalation_reason(old_dims, new_dims)
    assert "市场与坏账" in reason_line
    assert "18" in reason_line and "50" in reason_line
    assert "坏账率 0.30%，需关注" in reason_line
    assert detail == {"dimension": "market", "label": "市场与坏账",
                       "old_score": 18, "new_score": 50, "delta": 32}


def test_escalation_reason_ties_broken_by_dimensions_order():
    # contract (weight 0.20, earlier in DIMENSIONS) and yield (weight 0.05,
    # later) both move by +10 — contract must win the tie.
    old_dims = {"contract": 10, "yield": 10}
    new_dims = [
        {"key": "contract", "label": "协议与合约", "score": 20, "notes": ""},
        {"key": "yield", "label": "收益异常", "score": 20, "notes": ""},
    ]
    _reason_line, detail = _escalation_reason(old_dims, new_dims)
    assert detail["dimension"] == "contract"


def test_escalation_reason_no_old_dims():
    reason_line, detail = _escalation_reason(
        None, [{"key": "market", "label": "市场与坏账", "score": 50, "notes": ""}])
    assert reason_line == NO_HISTORY_TEXT
    assert detail is None


def test_escalation_reason_empty_new_dims():
    reason_line, detail = _escalation_reason({"market": 18}, [])
    assert reason_line == NO_HISTORY_TEXT
    assert detail is None


def test_escalation_reason_no_overlapping_keys():
    reason_line, detail = _escalation_reason(
        {"foo": 10}, [{"key": "market", "label": "市场与坏账", "score": 50, "notes": ""}])
    assert reason_line == NO_HISTORY_TEXT
    assert detail is None


def test_escalation_reason_no_positive_delta():
    old_dims = {"market": 50}
    new_dims = [{"key": "market", "label": "市场与坏账", "score": 30, "notes": ""}]
    reason_line, detail = _escalation_reason(old_dims, new_dims)
    assert reason_line == NO_HISTORY_TEXT
    assert detail is None


def test_escalation_reason_omits_notes_suffix_when_empty():
    old_dims = {"market": 18}
    new_dims = [{"key": "market", "label": "市场与坏账", "score": 50, "notes": ""}]
    reason_line, _detail = _escalation_reason(old_dims, new_dims)
    assert reason_line == "主要因：市场与坏账 18→50"


# ---------- fixtures ----------

@pytest.fixture
async def storage(tmp_path):
    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    await s.initialize()
    yield s
    await s.close()


@pytest.fixture
async def store(storage):
    return ConfigStore(storage._session_factory)


def _status_block(level, total=25.0, veto=None, error=False, dimensions=None):
    if error:
        return {"score": 0, "level": "critical", "checks": [],
                 "risk_model": {"error": "boom"}, "updated_at": None}
    return {"score": 8.0, "level": "ok", "checks": [],
             "risk_model": {"total": total, "level": level,
                              "veto_flags": veto or [],
                              "primary_chain": "base", "primary_asset": "USDC",
                              "apy": 5.0, "dimensions": dimensions or []},
             "updated_at": None}


def _patch_evaluate(by_protocol: dict):
    """Stub evaluate_protocol_status to return mapped status per protocol."""
    async def fake(protocol_name, *_a, **_kw):
        return by_protocol.get(protocol_name)
    return patch("stake_watch.risk.protocol_risk_monitor.evaluate_protocol_status",
                  side_effect=fake) if False else patch(
        "stake_watch.risk.protocol_status.evaluate_protocol_status",
        side_effect=fake)


# ---------- veto-trigger alert ----------

@pytest.mark.asyncio
async def test_veto_flags_produce_critical_alert(store, storage):
    await store.add_protocol(name="aave_v3_base", chain="base",
                              collector="defillama", enabled=True)
    with _patch_evaluate({"aave_v3_base":
            _status_block("D", veto=["稳定币价格 $0.9700 < $0.98"])}):
        alerts = await run_risk_monitor(storage, store, cooldown_minutes=0)
    assert len(alerts) == 1
    a = alerts[0]
    assert a.severity == Severity.CRITICAL
    assert "触发风险否决" in a.title
    assert "0.9700" in a.message
    # Persisted
    saved = await storage.get_recent_alerts()
    assert len(saved) == 1


@pytest.mark.asyncio
async def test_no_veto_no_alert(store, storage):
    await store.add_protocol(name="aave_v3_base", chain="base",
                              collector="defillama")
    with _patch_evaluate({"aave_v3_base": _status_block("A")}):
        alerts = await run_risk_monitor(storage, store, cooldown_minutes=0)
    assert alerts == []


# ---------- level escalation ----------

@pytest.mark.asyncio
async def test_level_escalation_emits_warning(store, storage):
    await store.add_protocol(name="aave_v3_base", chain="base",
                              collector="defillama")
    await store.set_setting("risk_monitor.last_level.aave_v3_base", "A")
    with _patch_evaluate({"aave_v3_base": _status_block("C")}):
        alerts = await run_risk_monitor(storage, store, cooldown_minutes=0)
    assert len(alerts) == 1
    assert alerts[0].severity == Severity.WARNING
    assert "A → C" in alerts[0].title


@pytest.mark.asyncio
async def test_level_escalation_to_e_is_critical(store, storage):
    await store.add_protocol(name="aave_v3_base", chain="base",
                              collector="defillama")
    await store.set_setting("risk_monitor.last_level.aave_v3_base", "D")
    with _patch_evaluate({"aave_v3_base": _status_block("E")}):
        alerts = await run_risk_monitor(storage, store, cooldown_minutes=0)
    assert alerts[0].severity == Severity.CRITICAL


@pytest.mark.asyncio
async def test_escalation_alert_includes_reason_with_prior_dimensions(store, storage):
    await store.add_protocol(name="aave_v3_base", chain="base",
                              collector="defillama")
    await store.set_setting("risk_monitor.last_level.aave_v3_base", "A")
    await store.set_setting("risk_monitor.last_evaluation.aave_v3_base", {
        "total": 17.0, "level": "A", "veto_flags": [],
        "primary_chain": "base", "primary_asset": "USDC",
        "dimensions": {"contract": 10, "market": 18, "liquidity": 12,
                        "collateral_oracle": 18, "governance": 10,
                        "stablecoin": 12, "chain": 5, "yield": 10},
        "evaluated_at": "2026-08-01T00:00:00+00:00",
    })
    new_dims = [
        {"key": "contract", "label": "协议与合约", "weight": 0.20, "score": 10,
         "notes": "", "source": "curated"},
        {"key": "market", "label": "市场与坏账", "weight": 0.20, "score": 50,
         "notes": "坏账率 0.30%，需关注", "source": "live"},
        {"key": "liquidity", "label": "提现流动性", "weight": 0.15, "score": 12,
         "notes": "", "source": "curated"},
        {"key": "collateral_oracle", "label": "抵押品/预言机", "weight": 0.15,
         "score": 18, "notes": "", "source": "curated"},
        {"key": "governance", "label": "管理与治理", "weight": 0.10, "score": 10,
         "notes": "", "source": "curated"},
        {"key": "stablecoin", "label": "稳定币资产", "weight": 0.08, "score": 12,
         "notes": "", "source": "curated"},
        {"key": "chain", "label": "链与基础设施", "weight": 0.07, "score": 5,
         "notes": "", "source": "curated"},
        {"key": "yield", "label": "收益异常", "weight": 0.05, "score": 10,
         "notes": "", "source": "curated"},
    ]
    block = _status_block("C", total=31.0, dimensions=new_dims)
    with _patch_evaluate({"aave_v3_base": block}):
        alerts = await run_risk_monitor(storage, store, cooldown_minutes=0)
    assert len(alerts) == 1
    a = alerts[0]
    assert "市场与坏账" in a.message
    assert "18→50" in a.message
    assert "坏账率 0.30%，需关注" in a.message
    assert a.details["escalation_reason"] == {
        "dimension": "market", "label": "市场与坏账",
        "old_score": 18, "new_score": 50, "delta": 32}


@pytest.mark.asyncio
async def test_escalation_alert_falls_back_without_prior_dimensions(store, storage):
    await store.add_protocol(name="aave_v3_base", chain="base",
                              collector="defillama")
    await store.set_setting("risk_monitor.last_level.aave_v3_base", "A")
    # No last_evaluation seeded at all — simulates a pre-feature install where
    # only last_level was ever recorded.
    with _patch_evaluate({"aave_v3_base": _status_block("C")}):
        alerts = await run_risk_monitor(storage, store, cooldown_minutes=0)
    assert len(alerts) == 1
    assert "无历史维度数据" in alerts[0].message
    assert alerts[0].details["escalation_reason"] is None


@pytest.mark.asyncio
async def test_level_drop_does_not_alert(store, storage):
    await store.add_protocol(name="aave_v3_base", chain="base",
                              collector="defillama")
    await store.set_setting("risk_monitor.last_level.aave_v3_base", "D")
    with _patch_evaluate({"aave_v3_base": _status_block("B")}):
        alerts = await run_risk_monitor(storage, store, cooldown_minutes=0)
    assert alerts == []


@pytest.mark.asyncio
async def test_last_level_persisted_for_next_run(store, storage):
    await store.add_protocol(name="aave_v3_base", chain="base",
                              collector="defillama")
    with _patch_evaluate({"aave_v3_base": _status_block("B")}):
        await run_risk_monitor(storage, store, cooldown_minutes=0)
    assert await store.get_setting("risk_monitor.last_level.aave_v3_base") == "B"


@pytest.mark.asyncio
async def test_last_evaluation_full_block_persisted(store, storage):
    """Frontend reads risk_monitor.last_evaluation.{name} to display live values
    alongside cached baseline — make sure every successful run writes it."""
    await store.add_protocol(name="aave_v3_base", chain="base",
                              collector="defillama")
    block = _status_block("C", total=31.0, veto=["foo"])
    with _patch_evaluate({"aave_v3_base": block}):
        await run_risk_monitor(storage, store, cooldown_minutes=0)
    ev = await store.get_setting("risk_monitor.last_evaluation.aave_v3_base")
    assert ev is not None
    assert ev["total"] == 31.0
    assert ev["level"] == "C"
    assert ev["veto_flags"] == ["foo"]
    assert "evaluated_at" in ev


@pytest.mark.asyncio
async def test_last_evaluation_persists_dimensions(store, storage):
    """Dimension scores must be snapshotted every run so the NEXT run can
    diff against them to explain a future escalation."""
    from stake_watch.risk.risk_model import DIM_KEYS

    await store.add_protocol(name="aave_v3_base", chain="base",
                              collector="defillama")
    dims = [{"key": k, "label": k, "weight": 0.1, "score": 20.0,
             "notes": "", "source": "curated"} for k in DIM_KEYS]
    block = _status_block("B", dimensions=dims)
    with _patch_evaluate({"aave_v3_base": block}):
        await run_risk_monitor(storage, store, cooldown_minutes=0)
    ev = await store.get_setting("risk_monitor.last_evaluation.aave_v3_base")
    assert ev["dimensions"] == {k: 20.0 for k in DIM_KEYS}


# ---------- cooldown ----------

@pytest.mark.asyncio
async def test_cooldown_suppresses_duplicate_veto(store, storage):
    await store.add_protocol(name="aave_v3_base", chain="base",
                              collector="defillama")
    block = _status_block("D", veto=["foo"])
    with _patch_evaluate({"aave_v3_base": block}):
        first = await run_risk_monitor(storage, store, cooldown_minutes=60)
        second = await run_risk_monitor(storage, store, cooldown_minutes=60)
    assert len(first) == 1 and len(second) == 0


@pytest.mark.asyncio
async def test_cooldown_zero_disables(store, storage):
    await store.add_protocol(name="aave_v3_base", chain="base",
                              collector="defillama")
    block = _status_block("D", veto=["foo"])
    with _patch_evaluate({"aave_v3_base": block}):
        first = await run_risk_monitor(storage, store, cooldown_minutes=0)
        second = await run_risk_monitor(storage, store, cooldown_minutes=0)
    assert len(first) == 1 and len(second) == 1


# ---------- notifier integration + safety ----------

@pytest.mark.asyncio
async def test_notifier_invoked_for_each_new_alert(store, storage):
    await store.add_protocol(name="aave_v3_base", chain="base",
                              collector="defillama")
    notifier = AsyncMock()
    notifier.send = AsyncMock(return_value=True)
    with _patch_evaluate({"aave_v3_base":
                           _status_block("D", veto=["foo"])}):
        await run_risk_monitor(storage, store, cooldown_minutes=0,
                                notifier=notifier)
    assert notifier.send.await_count == 1


@pytest.mark.asyncio
async def test_disabled_protocols_skipped(store, storage):
    await store.add_protocol(name="aave_v3_base", chain="base",
                              collector="defillama", enabled=False)
    with _patch_evaluate({"aave_v3_base":
                           _status_block("D", veto=["foo"])}):
        alerts = await run_risk_monitor(storage, store, cooldown_minutes=0)
    assert alerts == []


@pytest.mark.asyncio
async def test_error_in_evaluate_does_not_break_loop(store, storage):
    await store.add_protocol(name="a", chain="base", collector="defillama")
    await store.add_protocol(name="b", chain="base", collector="defillama")

    async def fake(name, *_a, **_kw):
        if name == "a":
            raise RuntimeError("boom")
        return _status_block("D", veto=["foo"])

    with patch("stake_watch.risk.protocol_status.evaluate_protocol_status",
                 side_effect=fake):
        alerts = await run_risk_monitor(storage, store, cooldown_minutes=0)
    assert len(alerts) == 1
    assert alerts[0].protocol == "b"
