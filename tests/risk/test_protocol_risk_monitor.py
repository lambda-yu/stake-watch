"""Tests for the periodic risk monitor that emits veto/level alerts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from stake_watch.models.alert import Alert, RuleType, Severity
from stake_watch.risk.protocol_risk_monitor import (
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


def _status_block(level, total=25.0, veto=None, error=False):
    if error:
        return {"score": 0, "level": "critical", "checks": [],
                 "risk_model": {"error": "boom"}, "updated_at": None}
    return {"score": 8.0, "level": "ok", "checks": [],
             "risk_model": {"total": total, "level": level,
                              "veto_flags": veto or [],
                              "primary_chain": "base", "primary_asset": "USDC",
                              "apy": 5.0, "dimensions": []},
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
