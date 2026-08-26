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

Keep the existing `risk_monitor.last_level.{name}` read exactly as-is — it
remains the sole input to `_is_escalation(last_level, level)`. Do not touch
this path; escalation detection must keep working even when
`last_evaluation.{name}` doesn't exist yet (e.g. upgrading from a pre-feature
install that only ever wrote `last_level`).

Additionally, read `risk_monitor.last_evaluation.{name}` (the full dict) as a
*separate, independent* lookup, used only to source `old_dims` for the reason
text in step 3. This value may be `None` (key never written) or present but
missing a `dimensions` field (written by a pre-feature version of this code).
Both cases are treated identically: `old_dims = None`.

### 3. Compute the escalation reason

At the point `_is_escalation(last_level, level)` is true:

- Let `old_dims = prior_last_evaluation.get("dimensions") if prior_last_evaluation else None`
  (`None` if this is the first evaluation ever recorded for this protocol, or
  a pre-feature `last_evaluation` without a `dimensions` field).
- Let `new_dims = {d["key"]: d["score"] for d in rm.get("dimensions", [])}`
  (may be `{}` if `rm["dimensions"]` is empty/absent).
- If `old_dims` is present **and** `new_dims` is non-empty: for each key
  present in *both* `old_dims` and `new_dims`, compute
  `delta = new_dims[k] - old_dims[k]`. Keys missing from either side are
  skipped (not treated as zero-delta candidates). Pick the key with the max
  delta among the remaining candidates (ties broken by `DIMENSIONS`
  declaration order, which is already weight-descending). Only treat it as
  "the reason" if `delta > 0` and at least one candidate key existed — if no
  dimension increased, or there were no overlapping keys, fall back to the
  no-history message.
- Build a human-readable line using the dimension's `label` and `notes`
  already present in `rm["dimensions"]` for the *new* evaluation:
  ```
  主要因：{label} {old_score:.0f}→{new_score:.0f}{f'，{notes}' if notes else ''}
  ```
  Example: `主要因：市场与坏账 18→50，坏账率 0.30%，需关注`
- In every other case (no attributable dimension found — covers `old_dims is
  None`, `new_dims` empty, no overlapping keys, or no key with `delta > 0`):
  reason line is the fixed string `（无历史维度数据，无法定位具体原因）`.
  The alert is still emitted (per user decision) — just without an
  attributable cause.

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
  (`None` whenever the fallback "no attributable cause" text is used — see
  step 3's fallback conditions). This lets the frontend or other consumers
  render the reason without re-parsing the message string.

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
   — when `dimensions` is empty, `new_dims` is `{}`, which per step 3 has no
   overlapping keys with `old_dims` (or `old_dims` is itself `None` since
   these tests never seed `last_evaluation.dimensions`), so the code takes
   the "no attributable cause" fallback branch without raising. This only
   affects the *message wording* of already-passing escalation tests;
   verified none of them assert on exact message content beyond `title` and
   `severity` (checked against `test_protocol_risk_monitor.py:97-126`), so
   they remain green unmodified.

## Non-goals

- No changes to `risk_model.py` scoring logic itself.
- No change to veto-alert wording.
- No UI/frontend changes — `escalation_reason` is exposed in `details` for
  future frontend use, but rendering it is out of scope for this change.
