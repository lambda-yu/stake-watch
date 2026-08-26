# Risk Escalation Reason Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When `run_risk_monitor()` emits a risk-level-escalation alert (A→B, B→C, …), the alert message states *which* risk dimension moved the most since the last evaluation and by how much, instead of only stating the old/new level.

**Architecture:** Add a pure, synchronous helper function `_escalation_reason(old_dims, new_dims)` in `protocol_risk_monitor.py` that diffs the previous per-dimension score snapshot against the current one and returns a human-readable reason line plus a structured detail dict. Persist the current per-dimension scores into the existing `risk_monitor.last_evaluation.{name}` JSON blob (already written every run) so the next run has a baseline to diff against. Wire the helper into the existing escalation branch of `run_risk_monitor()`.

**Tech Stack:** Python 3.12, pytest + pytest-asyncio, existing `ConfigStore` (SQLite-backed JSON key/value settings).

**Spec:** `docs/superpowers/specs/2026-08-26-risk-escalation-reason-design.md`

---

## Chunk 1: Escalation reason helper, persistence, and wiring

### Task 1: Pure helper function `_escalation_reason()`

**Files:**
- Modify: `src/stake_watch/risk/protocol_risk_monitor.py` (add import + function near top, after `_is_escalation`)
- Test: `tests/risk/test_protocol_risk_monitor.py` (new test functions)

This function has zero I/O — it takes two plain data structures and returns a tuple. Keeping it synchronous and dependency-free means it can be unit-tested directly without any async fixtures, DB, or mocking.

- [ ] **Step 1: Write the failing tests**

Add to `tests/risk/test_protocol_risk_monitor.py`, near the top (after the `_is_escalation` tests, before the `# ---------- fixtures ----------` section):

First, update the existing top-of-file import in `tests/risk/test_protocol_risk_monitor.py` to also pull in `_escalation_reason`:

```python
from stake_watch.risk.protocol_risk_monitor import (
    _escalation_reason,
    _is_escalation,
    run_risk_monitor,
)
```

Then add the new tests, near the top (after the `_is_escalation` tests, before the `# ---------- fixtures ----------` section):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/user/yu/code/stake-watch && uv run pytest tests/risk/test_protocol_risk_monitor.py -v -k escalation_reason`

Expected: FAIL with `ImportError: cannot import name '_escalation_reason'` (function doesn't exist yet).

- [ ] **Step 3: Implement `_escalation_reason()`**

In `src/stake_watch/risk/protocol_risk_monitor.py`, add this import near the top (with the other `stake_watch.risk` imports):

```python
from stake_watch.risk.risk_model import DIM_KEYS
```

Add this function directly after `_is_escalation()` (after line 32):

```python
_NO_HISTORY_REASON = "（无历史维度数据，无法定位具体原因）"


def _escalation_reason(old_dims: dict[str, float] | None,
                        new_dims: list[dict]) -> tuple[str, dict | None]:
    """Identify which risk dimension increased the most since the last
    evaluation, for use in a level-escalation alert message.

    old_dims: previous {dimension_key: score} snapshot, or None if no prior
        snapshot with dimension data exists (first-ever evaluation, or a
        pre-feature `last_evaluation` blob that predates this field).
    new_dims: current evaluation's `risk_model["dimensions"]` list, each
        entry shaped like {"key": ..., "label": ..., "score": ..., "notes": ...}.

    Returns (reason_line, escalation_reason_detail). `escalation_reason_detail`
    is None whenever no dimension could be attributed as the cause (no prior
    data, no overlapping keys, or no dimension that increased).
    """
    if not old_dims or not new_dims:
        return _NO_HISTORY_REASON, None

    new_by_key = {d["key"]: d for d in new_dims}
    best_key = None
    best_delta = 0.0
    for key in DIM_KEYS:  # fixed, weight-descending order for deterministic tie-break
        if key not in old_dims or key not in new_by_key:
            continue
        delta = new_by_key[key]["score"] - old_dims[key]
        if delta > best_delta:
            best_delta = delta
            best_key = key

    if best_key is None:
        return _NO_HISTORY_REASON, None

    d = new_by_key[best_key]
    old_score = old_dims[best_key]
    new_score = d["score"]
    notes = d.get("notes") or ""
    suffix = f"，{notes}" if notes else ""
    reason_line = f"主要因：{d['label']} {old_score:.0f}→{new_score:.0f}{suffix}"
    detail = {"dimension": best_key, "label": d["label"],
              "old_score": old_score, "new_score": new_score, "delta": best_delta}
    return reason_line, detail
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/user/yu/code/stake-watch && uv run pytest tests/risk/test_protocol_risk_monitor.py -v -k escalation_reason`

Expected: All 7 new tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/user/yu/code/stake-watch
git add src/stake_watch/risk/protocol_risk_monitor.py tests/risk/test_protocol_risk_monitor.py
git commit -m "feat(risk): add pure helper to identify top-moving dimension for escalation alerts"
```

---

### Task 2: Persist per-dimension scores in `last_evaluation`

**Files:**
- Modify: `src/stake_watch/risk/protocol_risk_monitor.py:140-147` (the always-run `last_evaluation` write at the end of the per-protocol loop)
- Test: `tests/risk/test_protocol_risk_monitor.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/risk/test_protocol_risk_monitor.py`, near `test_last_evaluation_full_block_persisted` (in the cooldown-adjacent block; put it right after that test):

```python
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
```

This test requires `_status_block()` to accept a `dimensions` keyword argument. Update the helper (defined near the top of the fixtures section, currently at line 45-54) to:

```python
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
```

(The only change is the new `dimensions=None` parameter and using `dimensions or []` instead of the hardcoded `[]`. All existing call sites that don't pass `dimensions` keep getting `[]`, so no other test changes.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/user/yu/code/stake-watch && uv run pytest tests/risk/test_protocol_risk_monitor.py::test_last_evaluation_persists_dimensions -v`

Expected: FAIL with `KeyError: 'dimensions'` (the persisted blob doesn't have that field yet).

- [ ] **Step 3: Implement the persistence change**

In `src/stake_watch/risk/protocol_risk_monitor.py`, find the always-run block near the end of the per-protocol loop (currently lines 138-147):

```python
        # Always update last-seen evaluation so frontend can show live values
        # alongside the cached baseline (and so escalation deltas survive restarts).
        if level:
            await config_store.set_setting(f"risk_monitor.last_level.{p.name}", level)
            await config_store.set_setting(
                f"risk_monitor.last_evaluation.{p.name}",
                {"total": rm.get("total"), "level": level,
                 "veto_flags": veto_flags,
                 "primary_chain": chain, "primary_asset": asset,
                 "evaluated_at": datetime.now(timezone.utc).isoformat()})
```

Replace with:

```python
        # Always update last-seen evaluation so frontend can show live values
        # alongside the cached baseline (and so escalation deltas survive restarts).
        if level:
            await config_store.set_setting(f"risk_monitor.last_level.{p.name}", level)
            dims_snapshot = {d["key"]: d["score"] for d in (rm.get("dimensions") or [])}
            await config_store.set_setting(
                f"risk_monitor.last_evaluation.{p.name}",
                {"total": rm.get("total"), "level": level,
                 "veto_flags": veto_flags,
                 "primary_chain": chain, "primary_asset": asset,
                 "dimensions": dims_snapshot,
                 "evaluated_at": datetime.now(timezone.utc).isoformat()})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/user/yu/code/stake-watch && uv run pytest tests/risk/test_protocol_risk_monitor.py -v`

Expected: All tests PASS, including the pre-existing `test_last_evaluation_full_block_persisted` (its assertions only check `total`, `level`, `veto_flags`, `evaluated_at` — adding a new `dimensions` key doesn't break it).

- [ ] **Step 5: Commit**

```bash
cd /Users/user/yu/code/stake-watch
git add src/stake_watch/risk/protocol_risk_monitor.py tests/risk/test_protocol_risk_monitor.py
git commit -m "feat(risk): persist per-dimension scores in last_evaluation snapshot"
```

---

### Task 3: Wire the reason into the escalation alert

**Files:**
- Modify: `src/stake_watch/risk/protocol_risk_monitor.py:111-136` (the escalation-alert branch)
- Test: `tests/risk/test_protocol_risk_monitor.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/risk/test_protocol_risk_monitor.py`, in the `# ---------- level escalation ----------` section (after `test_level_escalation_to_e_is_critical`, before `test_level_drop_does_not_alert`):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/user/yu/code/stake-watch && uv run pytest tests/risk/test_protocol_risk_monitor.py -v -k "escalation_alert_includes_reason or escalation_alert_falls_back"`

Expected: FAIL — `assert "市场与坏账" in a.message` fails because the message doesn't contain any dimension reasoning yet; `a.details["escalation_reason"]` raises `KeyError` because that key doesn't exist yet.

- [ ] **Step 3: Implement the wiring**

In `src/stake_watch/risk/protocol_risk_monitor.py`, find the escalation branch (currently lines 111-136):

```python
        # 2. Risk level escalation → WARNING (or CRITICAL on E)
        last_level = await config_store.get_setting(f"risk_monitor.last_level.{p.name}")
        if _is_escalation(last_level, level):
            severity = Severity.CRITICAL if level == "E" else Severity.WARNING
            alert = Alert(
                rule_type=RuleType.PROTOCOL_EVENT,
                severity=severity,
                protocol=p.name, chain=chain,
                title=f"{p.name} 风险等级 {last_level} → {level}",
                message=f"综合风险评分 {rm.get('total')}，等级从 {last_level} 升至 {level}",
                details={"monitor_kind": "level_escalation",
                         "risk_total": rm.get("total"), "old_level": last_level,
                         "new_level": level, "primary_asset": asset,
                         "veto_flags": veto_flags},
                created_at=datetime.now(timezone.utc),
            )
            if not await _cooldown_blocks(storage, protocol=p.name, chain=chain,
                                           kind="level_escalation",
                                           cooldown_minutes=cooldown_minutes):
                await storage.save_alert(alert)
                emitted.append(alert)
                if notifier is not None:
                    try:
                        await notifier.send(alert)
                    except Exception as e:
                        logger.warning(f"notifier failed for {p.name}: {e}")
```

Replace with:

```python
        # 2. Risk level escalation → WARNING (or CRITICAL on E)
        last_level = await config_store.get_setting(f"risk_monitor.last_level.{p.name}")
        if _is_escalation(last_level, level):
            prior_evaluation = await config_store.get_setting(
                f"risk_monitor.last_evaluation.{p.name}")
            old_dims = (prior_evaluation or {}).get("dimensions")
            reason_line, escalation_reason = _escalation_reason(
                old_dims, rm.get("dimensions") or [])
            severity = Severity.CRITICAL if level == "E" else Severity.WARNING
            alert = Alert(
                rule_type=RuleType.PROTOCOL_EVENT,
                severity=severity,
                protocol=p.name, chain=chain,
                title=f"{p.name} 风险等级 {last_level} → {level}",
                message=(f"综合风险评分 {rm.get('total')}，"
                         f"等级从 {last_level} 升至 {level}\n{reason_line}"),
                details={"monitor_kind": "level_escalation",
                         "risk_total": rm.get("total"), "old_level": last_level,
                         "new_level": level, "primary_asset": asset,
                         "veto_flags": veto_flags,
                         "escalation_reason": escalation_reason},
                created_at=datetime.now(timezone.utc),
            )
            if not await _cooldown_blocks(storage, protocol=p.name, chain=chain,
                                           kind="level_escalation",
                                           cooldown_minutes=cooldown_minutes):
                await storage.save_alert(alert)
                emitted.append(alert)
                if notifier is not None:
                    try:
                        await notifier.send(alert)
                    except Exception as e:
                        logger.warning(f"notifier failed for {p.name}: {e}")
```

Note: `prior_evaluation` is read here — *before* the always-run block later in the loop overwrites `risk_monitor.last_evaluation.{name}` — so it correctly reflects the previous run's snapshot, not the current one.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/user/yu/code/stake-watch && uv run pytest tests/risk/test_protocol_risk_monitor.py -v -k "escalation_alert_includes_reason or escalation_alert_falls_back"`

Expected: Both new tests PASS.

- [ ] **Step 5: Run the full test file to check for regressions**

Run: `cd /Users/user/yu/code/stake-watch && uv run pytest tests/risk/test_protocol_risk_monitor.py -v`

Expected: All tests PASS (including the pre-existing `test_level_escalation_emits_warning` and `test_level_escalation_to_e_is_critical`, which only assert on `title` and `severity` and are unaffected by the new message content).

- [ ] **Step 6: Run the full project test suite**

Run: `cd /Users/user/yu/code/stake-watch && uv run pytest tests/ -v`

Expected: All tests PASS, no regressions anywhere else in the codebase (no other module reads `risk_monitor.last_evaluation.*` or `risk_monitor.last_level.*` besides this file and its tests — confirmed during spec review).

- [ ] **Step 7: Commit**

```bash
cd /Users/user/yu/code/stake-watch
git add src/stake_watch/risk/protocol_risk_monitor.py tests/risk/test_protocol_risk_monitor.py
git commit -m "feat(risk): state the top-moving dimension as the reason in escalation alerts"
```

---

## Non-goals (carried from spec)

- No changes to `risk_model.py` scoring logic itself.
- No change to veto-alert wording.
- No UI/frontend changes — `escalation_reason` is exposed in `details` for future frontend use, but rendering it is out of scope for this plan.
