# Risk Escalation Reason — Design

## Problem

`run_risk_monitor()` in `src/stake_watch/risk/protocol_risk_monitor.py` emits a
WARNING/CRITICAL alert when a protocol's risk level escalates (e.g. A→B), but
the alert message only states the score and old→new level:

```
{p.name} 风险等级 A → C
综合风险评分 31.0，等级从 A 升至 C
```

It never says *why* the score moved. The 8-dimension breakdown
(`risk_model.dimensions`, from `risk/risk_model.py`) is already computed on
every evaluation but is discarded after producing the total — only the total
and level are persisted (`risk_monitor.last_evaluation.{name}`).

## Goal

When emitting a level-escalation alert, identify which dimension moved the
most since the last evaluation and state it as the reason, using data already
computed by `evaluate_protocol_status()` — no new data sources.

## Approach

### 1. Persist dimension scores in `last_evaluation`

`run_risk_monitor()` already writes `risk_monitor.last_evaluation.{name}`
at the end of every loop iteration (line ~142-147 of
`protocol_risk_monitor.py`). Extend that JSON blob with a `dimensions` field:

```python
{"total": ..., "level": ..., "veto_flags": ..., "primary_chain": ...,
 "primary_asset": ..., "evaluated_at": ...,
 "dimensions": {"contract": 10, "market": 18, "liquidity": 12, ...}}  # NEW
```

Source: `rm.get("dimensions")` (list of `{key, label, weight, score, notes,
source}`) already present in the `status["risk_model"]` block returned by
`evaluate_protocol_status()`. Flatten to `{key: score}` for storage.

### 2. Read prior dimensions before overwriting

Currently the monitor reads only `risk_monitor.last_level.{name}` (a bare
string) for the escalation check. Switch to reading the full
`risk_monitor.last_evaluation.{name}` dict instead — it already contains
`level`, and after step 1 will also contain the previous `dimensions`. This
replaces the separate `last_level` read (the `level` field inside
`last_evaluation` serves the same purpose), but keep `last_level` write/read
as-is for backward compatibility with anything else relying on it — no other
consumers found in the codebase, so this is just an internal read-path swap
with no external contract change.

### 3. Compute the escalation reason

At the point `_is_escalation(last_level, level)` is true:

- Let `old_dims = prior_last_evaluation.get("dimensions")` (may be `None` if
  this is the first evaluation ever recorded for this protocol, e.g. right
  after deploying this feature).
- Let `new_dims = {d["key"]: d["score"] for d in rm.get("dimensions", [])}`.
- If `old_dims` is present: for each key in `risk_model.DIMENSIONS` order,
  compute `delta = new_dims[k] - old_dims.get(k, new_dims[k])` (missing old
  key → treat as no change, delta 0). Pick the key with the max delta
  (ties broken by `DIMENSIONS` declaration order, which is already
  weight-descending). Only treat it as "the reason" if `delta > 0` — if no
  dimension increased (edge case: total rose from rounding/PRODUCT_TOTAL
  interpolation without a clear per-dim mover), fall back to the no-history
  message.
- Build a human-readable line using the dimension's `label` and `notes`
  already present in `rm["dimensions"]` for the *new* evaluation:
  ```
  主要因：{label} {old_score:.0f}→{new_score:.0f}{f'，{notes}' if notes else ''}
  ```
  Example: `主要因：市场与坏账 18→50，坏账率 0.30%，需关注`
- If `old_dims` is `None`: reason line is the fixed string
  `（无历史维度数据，无法定位具体原因）`. The alert is still emitted (per
  user decision) — just without an attributable cause.

### 4. Wire into the alert

- **Title**: unchanged — `f"{p.name} 风险等级 {last_level} → {level}"`. Stays
  short for Telegram notification previews.
- **Message**: append the reason line on a new line:
  ```python
  message = f"综合风险评分 {rm.get('total')}，等级从 {last_level} 升至 {level}\n{reason_line}"
  ```
- **details**: add a new key `escalation_reason`:
  ```python
  {"dimension": key, "label": label, "old_score": old_score,
   "new_score": new_score, "delta": delta} | None
  ```
  (`None` when no prior dimensions existed). This lets the frontend or other
  consumers render the reason without re-parsing the message string.

### 5. No change to veto-triggered alerts

Veto alerts (`veto_flags`) already state concrete, specific reasons (e.g.
"坏账率 0.30% > 0.2%"). No changes needed there.

## Testing

Extend `tests/risk/test_protocol_risk_monitor.py`:

1. **`test_escalation_reason_with_prior_dimensions`** — seed
   `risk_monitor.last_evaluation.aave_v3_base` with a `dimensions` dict where
   `market` is the biggest mover; assert the emitted alert's `message`
   contains the dimension label and old→new scores, and `details["escalation_reason"]["dimension"] == "market"`.
2. **`test_escalation_reason_without_prior_dimensions`** — seed only
   `risk_monitor.last_level.aave_v3_base` (no `last_evaluation`, simulating
   pre-feature state) and confirm the alert still fires with the "无历史维度数据" fallback text, `details["escalation_reason"] is None`.
3. **`test_last_evaluation_persists_dimensions`** — after a run, assert
   `risk_monitor.last_evaluation.{name}["dimensions"]` is a non-empty dict
   matching the 8 `DIM_KEYS`.
4. Update existing `_status_block()` test helper to accept an optional
   `dimensions` list so old tests (which pass `dimensions: []`) keep passing
   — when `dimensions` is empty, `new_dims` is `{}` and delta computation
   naturally falls back to "no dimension increased" behavior, but since this
   only affects the *message wording* of already-passing escalation tests,
   verify none of them assert on the exact message content beyond what's
   already covered (checked: they only assert `title` and `severity`, so
   safe).

## Non-goals

- No changes to `risk_model.py` scoring logic itself.
- No change to veto-alert wording.
- No UI/frontend changes — `escalation_reason` is exposed in `details` for
  future frontend use, but rendering it is out of scope for this change.
