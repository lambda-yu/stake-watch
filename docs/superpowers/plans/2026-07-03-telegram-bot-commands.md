# Telegram Bot Commands Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 4 slash commands (`/help`, `/protocols`, `/compare`, `/protocol <name>`) so users can pull protocol info on demand from Telegram, alongside existing scheduled pushes.

**Architecture:** New `TelegramCommandBot` class runs long-polling as a third asyncio task inside the main process (alongside FastAPI + APScheduler). Handlers dispatch to existing `send_protocols_report` / `send_comparison_screenshot`, plus a new `format_protocol_detail` for `/protocol`. Only messages from the configured `telegram.chat_id` are processed. Auto-starts when both `telegram.bot_token` and `telegram.chat_id` are set in DB config; otherwise silently disabled.

**Tech Stack:** Python 3.12+, asyncio, `python-telegram-bot >= 22.8` (`Application` + `CommandHandler`), SQLAlchemy (via existing `ConfigStore` / `Storage`), pytest + pytest-asyncio, `unittest.mock.AsyncMock` / `MagicMock`.

**Spec:** `docs/superpowers/specs/2026-07-03-telegram-bot-commands-design.md`

---

## File Structure

**Create:**
- `src/stake_watch/alerts/bot_commands.py` — `TelegramCommandBot` class + `format_help` + `format_protocol_detail` pure functions
- `tests/alerts/test_bot_commands.py` — tests for all new code

**Modify:**
- `src/stake_watch/alerts/formatter.py` — add public `format_tvl(v: float) -> str`
- `src/stake_watch/alerts/protocols_report.py` — migrate `_format_tvl` to `format_tvl` import (delete local copy)
- `src/stake_watch/main.py` — read `telegram.bot_token` / `chat_id`, start bot task, register shutdown
- `tests/alerts/test_protocols_report.py` — swap `_format_tvl` import for the public one

**Rationale for `bot_commands.py` being one file:** the class and its two helper pure functions all speak to the same command dispatch surface. Splitting them adds imports without helping isolation. If the file grows past ~250 lines during the work, split pure formatters out then; don't pre-optimize.

---

## Chunk 1: Public `format_tvl` helper

Migrate the existing `_format_tvl` in `protocols_report.py` to a public function in `alerts/formatter.py`. Both `protocols_report.py` and the new `bot_commands.py` will import it. This chunk lands first so later chunks can use it.

### Task 1.1: Add `format_tvl` to `alerts/formatter.py`

**Files:**
- Modify: `src/stake_watch/alerts/formatter.py`
- Test: `tests/alerts/test_formatter.py`

- [ ] **Step 1: Read the current formatter.py**

Run: `cat src/stake_watch/alerts/formatter.py`
Expected: You'll see the existing `format_alert` function. Add `format_tvl` alongside it.

- [ ] **Step 2: Write failing tests in `tests/alerts/test_formatter.py`**

Append to the file (create the file if it doesn't exist — but it does):

```python
from stake_watch.alerts.formatter import format_tvl


@pytest.mark.parametrize("v,expected", [
    (500, "$500"),
    (999, "$999"),
    (1_000, "$1K"),
    (2_400, "$2K"),
    (999_999, "$1000K"),
    (1_000_000, "$1.0M"),
    (1_200_000, "$1.2M"),
    (999_999_999, "$1000.0M"),
    (1_000_000_000, "$1.00B"),
    (3_400_000_000, "$3.40B"),
])
def test_format_tvl_scales(v, expected):
    assert format_tvl(v) == expected
```

Add `import pytest` at the top of the file (the current header doesn't import it).

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/alerts/test_formatter.py::test_format_tvl_scales -v`
Expected: FAIL with `ImportError: cannot import name 'format_tvl'`.

- [ ] **Step 4: Implement `format_tvl`**

Append to `src/stake_watch/alerts/formatter.py`:

```python
def format_tvl(v: float) -> str:
    """Format a USD TVL value with human-readable scale (K/M/B).

    Preserves the exact output of the previous ``protocols_report._format_tvl``
    so downstream reports stay identical after the migration.
    """
    if v >= 1e9:
        return f"${v/1e9:.2f}B"
    if v >= 1e6:
        return f"${v/1e6:.1f}M"
    if v >= 1e3:
        return f"${v/1e3:.0f}K"
    return f"${v:.0f}"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/alerts/test_formatter.py -v`
Expected: All parametrized cases PASS.

- [ ] **Step 6: Commit**

```bash
git add src/stake_watch/alerts/formatter.py tests/alerts/test_formatter.py
git commit -m "feat(formatter): add public format_tvl for TVL display

Extracted from protocols_report._format_tvl so bot_commands.py can
reuse the same K/M/B formatting without duplicating logic.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 1.2: Migrate `protocols_report.py` to the public helper

This is a mechanical refactor — no behavior change, so no red/green cycle. Verify green after the rename.

**Files:**
- Modify: `src/stake_watch/alerts/protocols_report.py`
- Modify: `tests/alerts/test_protocols_report.py`

- [ ] **Step 1: Delete the duplicated test in `test_protocols_report.py`**

Open `tests/alerts/test_protocols_report.py`. The parametrized `test_format_tvl_scales` there now duplicates the identical test in `test_formatter.py` (added in Task 1.1). Delete the duplicate along with the `_format_tvl` import line — the canonical coverage lives in `test_formatter.py`.

- [ ] **Step 2: Update remaining imports in `test_protocols_report.py`**

The file no longer needs `_format_tvl`. Change the import block to:

```python
from stake_watch.alerts.protocols_report import (
    _best_apy,
    format_protocols_report,
)
```

- [ ] **Step 3: In `protocols_report.py`, replace the local `_format_tvl`**

1. Add near the top of `src/stake_watch/alerts/protocols_report.py`: `from stake_watch.alerts.formatter import format_tvl`
2. Delete the local `_format_tvl` function (around lines 75-82 of the current file).
3. Replace all 5 call sites of `_format_tvl(` with `format_tvl(` inside `format_protocols_report`.

- [ ] **Step 4: Run alerts tests — all green**

Run: `uv run pytest tests/alerts/ -v`
Expected: All tests PASS (the previous `test_format_tvl_scales` from `test_protocols_report.py` is gone; the identical one in `test_formatter.py` still covers the behavior).

- [ ] **Step 5: Commit**

```bash
git add src/stake_watch/alerts/protocols_report.py tests/alerts/test_protocols_report.py
git commit -m "refactor(protocols-report): use public format_tvl helper

Mechanical: delete the local _format_tvl copy and its now-duplicate
test, import format_tvl from alerts.formatter so future callers
(bot_commands.py) don't fork the formatting.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 2: Pure formatting functions

`format_help` and `format_protocol_detail` are pure — no async, no I/O, no Telegram library required. Write them first with high coverage; the class in Chunk 3 will just call them.

### Task 2.1: Create `bot_commands.py` with `format_help`

**Files:**
- Create: `src/stake_watch/alerts/bot_commands.py`
- Test: `tests/alerts/test_bot_commands.py`

- [ ] **Step 1: Write the failing test**

Create `tests/alerts/test_bot_commands.py`:

```python
"""Tests for the interactive Telegram command bot."""
from __future__ import annotations

from stake_watch.alerts.bot_commands import format_help


# ---------- format_help ----------

def test_format_help_lists_all_four_commands():
    text = format_help()
    for cmd in ("/help", "/protocols", "/compare", "/protocol"):
        assert cmd in text, f"missing {cmd} in help output"
```

- [ ] **Step 2: Run test — verify it fails**

Run: `uv run pytest tests/alerts/test_bot_commands.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'stake_watch.alerts.bot_commands'`.

- [ ] **Step 3: Create the module skeleton with `format_help`**

Create `src/stake_watch/alerts/bot_commands.py`:

```python
"""Interactive Telegram command bot (long polling).

Runs alongside FastAPI + APScheduler as a third asyncio task in the main
process. Only messages from the configured `telegram.chat_id` are processed;
other chats are ignored silently.

Commands:
  /help              — command list
  /protocols         — trigger the full protocols report
  /compare           — trigger the comparison-page screenshot
  /protocol <name>   — single-protocol detail (case-insensitive match)
"""
from __future__ import annotations


def format_help() -> str:
    return (
        "🤖 Stake Watch 命令\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "/protocols  — 全部协议 APY / TVL 概览\n"
        "/compare    — 协议对比页面截图\n"
        "/protocol <名字>  — 单个协议详情\n"
        "/help       — 显示此帮助"
    )
```

- [ ] **Step 4: Run test — verify PASS**

Run: `uv run pytest tests/alerts/test_bot_commands.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stake_watch/alerts/bot_commands.py tests/alerts/test_bot_commands.py
git commit -m "feat(bot-commands): scaffold module with format_help

First slice of the interactive Telegram bot — pure formatter with
its test, no polling yet. Later tasks add format_protocol_detail
and the TelegramCommandBot class.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 2.2: `format_protocol_detail` — full chains_breakdown layout

**Files:**
- Modify: `src/stake_watch/alerts/bot_commands.py`
- Test: `tests/alerts/test_bot_commands.py`

- [ ] **Step 1: Write the failing test — full layout**

Append to `tests/alerts/test_bot_commands.py`:

```python
from datetime import datetime, timezone

from stake_watch.alerts.bot_commands import format_protocol_detail


def _make_stats(ts: datetime | None = None):
    """Cheap stand-in — the formatter only reads .timestamp."""
    class _S:
        timestamp = ts
    return _S()


def test_format_protocol_detail_full_layout():
    protocol = {
        "name": "Aave",
        "chain": "Ethereum",
        "enabled": True,
        "safety_score": 85,
        "risk_scores": {"liquidity": 90, "smart_contract": 80, "governance": 85},
    }
    chains_breakdown = [
        {
            "chain": "Ethereum",
            "by_asset": {
                "USDC": {"apy": 4.12, "tvl_usd": 1.2e9},
                "USDT": {"apy": 3.98, "tvl_usd": 8.9e8},
            },
        },
        {
            "chain": "Base",
            "by_asset": {"USDC": {"apy": 5.20, "tvl_usd": 1.2e8}},
        },
    ]
    stats = _make_stats(datetime(2026, 7, 3, 6, 20, tzinfo=timezone.utc))

    out = format_protocol_detail(
        protocol=protocol,
        chains_breakdown=chains_breakdown,
        stats=stats,
        tz_offset=8,
    )

    assert "📋 Aave" in out
    assert "链: Ethereum" in out
    assert "状态: 启用 ✓" in out
    assert "Safety Score: 85" in out
    assert "USDC" in out and "4.12" in out and "$1.20B" in out
    assert "USDT" in out and "3.98" in out and "$890.0M" in out
    assert "Base" in out
    assert "5.20" in out and "$120.0M" in out
    assert "liquidity 90" in out
    assert "smart_contract 80" in out
    assert "governance 85" in out
    assert "2026-07-03 14:20 UTC+8" in out
```

- [ ] **Step 2: Run test — verify FAIL**

Run: `uv run pytest tests/alerts/test_bot_commands.py::test_format_protocol_detail_full_layout -v`
Expected: FAIL — `ImportError: cannot import name 'format_protocol_detail'`.

- [ ] **Step 3: Implement `format_protocol_detail`**

Append to `src/stake_watch/alerts/bot_commands.py`:

```python
from typing import Any

from stake_watch.alerts.formatter import format_tvl
from stake_watch.alerts.timezone import format_time


_MAX_MESSAGE_CHARS = 3800  # Telegram hard limit is 4096; leave headroom.


def format_protocol_detail(
    protocol: dict[str, Any],
    chains_breakdown: list[dict] | None,
    stats: Any,
    tz_offset: int = 8,
) -> str:
    """Compose the single-protocol detail message body.

    ``protocol`` is a mapping (or ORM row exposing attribute access via .name,
    .chain, .enabled, .safety_score, .risk_scores). ``chains_breakdown`` is
    the per-chain / per-asset structure stored under
    ``protocols.<name>.chains``. ``stats`` may be None or an object with a
    ``.timestamp`` attribute (a UTC-aware ``datetime``).

    Returns a plain-text message body, truncated to Telegram's per-message
    limit if necessary.
    """
    p = _view(protocol)
    lines: list[str] = [f"📋 {p['name']}", "━━━━━━━━━━━━━━━━━━━━━━"]

    lines.append(f"链: {p['chain']}")
    lines.append(f"状态: {'启用 ✓' if p.get('enabled') else '停用 ✗'}")

    safety = p.get("safety_score")
    if safety is not None:
        lines.append(f"Safety Score: {safety}")

    if chains_breakdown:
        lines.append("")
        lines.append("各链池子:")
        primary_chain = (p.get("chain") or "").upper()
        chains_sorted = sorted(
            chains_breakdown,
            key=lambda c: 0 if (c.get("chain") or "").upper() == primary_chain else 1,
        )
        for c in chains_sorted:
            lines.append(f"  {c.get('chain', '?')}")
            by_asset = c.get("by_asset") or {}
            for asset in _ordered_assets(by_asset):
                info = by_asset[asset]
                apy = info.get("apy")
                tvl = info.get("tvl_usd")
                apy_str = f"{apy:.2f}%" if apy is not None else "—"
                tvl_str = format_tvl(tvl) if tvl else "—"
                lines.append(f"    {asset}  APY {apy_str}  TVL {tvl_str}")
    elif stats is not None and getattr(stats, "pools", None):
        # fallback: single-chain / single-pool from ProtocolStats
        lines.append("")
        default = _pick_default_pool(stats.pools)
        asset = default.asset
        apy = getattr(default, "supply_apy", None)
        tvl = getattr(stats, "tvl_usd", None)
        apy_str = f"{apy:.2f}%" if apy is not None else "—"
        tvl_str = format_tvl(float(tvl)) if tvl else "—"
        lines.append(
            f"{(p.get('chain') or '').upper()} {asset}: APY {apy_str}  TVL {tvl_str}"
        )

    risk = p.get("risk_scores") or {}
    if isinstance(risk, dict) and risk:
        parts = [f"{k} {v}" for k, v in risk.items()]
        lines.append("")
        lines.append("风险评分: " + " / ".join(parts))

    ts = getattr(stats, "timestamp", None) if stats is not None else None
    if ts is not None:
        lines.append("")
        lines.append(f"最新数据: {format_time(ts, tz_offset)}")

    body = "\n".join(lines)
    if len(body) > _MAX_MESSAGE_CHARS:
        body = body[: _MAX_MESSAGE_CHARS - 20].rstrip() + "\n...(已截断)"
    return body


def _view(protocol: Any) -> dict:
    """Uniform dict view over ORM row or plain dict."""
    if isinstance(protocol, dict):
        return protocol
    return {
        "name": getattr(protocol, "name", None),
        "chain": getattr(protocol, "chain", None),
        "enabled": getattr(protocol, "enabled", None),
        "safety_score": getattr(protocol, "safety_score", None),
        "risk_scores": getattr(protocol, "risk_scores", None),
    }


def _ordered_assets(by_asset: dict) -> list[str]:
    """USDC first, USDT second, then anything else in dict order."""
    preferred = [a for a in ("USDC", "USDT") if a in by_asset]
    others = [a for a in by_asset if a not in preferred]
    return preferred + others


def _pick_default_pool(pools):
    for pool in pools:
        if "USDC" in (getattr(pool, "asset", "") or "").upper():
            return pool
    return pools[0]
```

- [ ] **Step 4: Run test — verify PASS**

Run: `uv run pytest tests/alerts/test_bot_commands.py::test_format_protocol_detail_full_layout -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stake_watch/alerts/bot_commands.py tests/alerts/test_bot_commands.py
git commit -m "feat(bot-commands): format_protocol_detail (chains_breakdown layout)

Compose the per-chain / per-asset detail message from ProtocolConfigRow
plus the cached chains_breakdown setting. USDC ordered first, primary
chain first, TVL formatted via the public format_tvl helper.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 2.3: `format_protocol_detail` — edge cases

**Files:**
- Test: `tests/alerts/test_bot_commands.py`

- [ ] **Step 1: Write failing edge-case tests**

Append to `tests/alerts/test_bot_commands.py`:

```python
class _Pool:
    def __init__(self, asset, supply_apy):
        self.asset = asset
        self.supply_apy = supply_apy


class _Stats:
    def __init__(self, timestamp=None, tvl_usd=None, pools=None):
        self.timestamp = timestamp
        self.tvl_usd = tvl_usd
        self.pools = pools or []


def test_format_protocol_detail_fallback_when_no_chains_breakdown():
    protocol = {"name": "Aave", "chain": "Ethereum", "enabled": True,
                "safety_score": 85, "risk_scores": None}
    stats = _Stats(
        timestamp=datetime(2026, 7, 3, 6, 20, tzinfo=timezone.utc),
        tvl_usd=1.2e9,
        pools=[_Pool("USDC", 4.12)],
    )
    out = format_protocol_detail(protocol, chains_breakdown=None,
                                 stats=stats, tz_offset=8)
    assert "各链池子" not in out
    assert "ETHEREUM USDC: APY 4.12%" in out
    assert "$1.20B" in out


def test_format_protocol_detail_omits_optional_sections_when_missing():
    protocol = {"name": "X", "chain": "Base", "enabled": False,
                "safety_score": None, "risk_scores": {}}
    out = format_protocol_detail(protocol, chains_breakdown=None,
                                 stats=None, tz_offset=8)
    assert "停用 ✗" in out
    assert "Safety Score" not in out
    assert "风险评分" not in out
    assert "最新数据" not in out


def test_format_protocol_detail_truncates_long_output():
    # Build a chains_breakdown big enough to blow past 3800 chars.
    big = [
        {"chain": f"Chain-{i}", "by_asset": {
            "USDC": {"apy": 1.23, "tvl_usd": 1e8},
            "USDT": {"apy": 4.56, "tvl_usd": 2e8},
        }}
        for i in range(200)
    ]
    protocol = {"name": "Huge", "chain": "Chain-0", "enabled": True,
                "safety_score": 50, "risk_scores": {"x": 1}}
    out = format_protocol_detail(protocol, chains_breakdown=big,
                                 stats=None, tz_offset=8)
    assert len(out) <= 3800
    assert out.endswith("...(已截断)")


def test_format_protocol_detail_accepts_row_like_object():
    class _Row:
        name = "Aave"
        chain = "Ethereum"
        enabled = True
        safety_score = 85
        risk_scores = None
    out = format_protocol_detail(_Row(), chains_breakdown=None,
                                 stats=None, tz_offset=8)
    assert "📋 Aave" in out
    assert "状态: 启用 ✓" in out
```

- [ ] **Step 2: Run tests — verify all four PASS**

Run: `uv run pytest tests/alerts/test_bot_commands.py -v`
Expected: PASS. These are additional characterization tests; the implementation from Task 2.2 should already handle them.

- [ ] **Step 3: If any test fails, that's a real bug in Task 2.2 — fix minimally**

Only touch `format_protocol_detail` and its private helpers. Common gotchas:
- ORM row without `risk_scores` returns `None` → `_view` maps to `None`, current guard `isinstance(risk, dict) and risk` handles it.
- Empty `risk_scores` dict (`{}`) must be silenced — the `and risk` clause handles that.
- Do not change assertions to match a buggy implementation.

- [ ] **Step 4: Run tests — verify all PASS**

Run: `uv run pytest tests/alerts/test_bot_commands.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/alerts/test_bot_commands.py src/stake_watch/alerts/bot_commands.py
git commit -m "test(bot-commands): edge cases for format_protocol_detail

Cover fallback layout, missing safety_score/risk_scores/timestamp,
Telegram 3800-char truncation, and ProtocolConfigRow attribute access.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 3: `TelegramCommandBot` class

Handlers, authorization, lifecycle. Everything below stays pure-python + `unittest.mock` — no real polling in tests.

### Task 3.1: `TelegramCommandBot.__init__` + `_authorized`

**Files:**
- Modify: `src/stake_watch/alerts/bot_commands.py`
- Test: `tests/alerts/test_bot_commands.py`

- [ ] **Step 1: Write failing tests for the guard**

Append to `tests/alerts/test_bot_commands.py`:

```python
from unittest.mock import MagicMock

from stake_watch.alerts.bot_commands import TelegramCommandBot


def _make_update(chat_id: int | None):
    upd = MagicMock()
    if chat_id is None:
        upd.effective_chat = None
    else:
        upd.effective_chat = MagicMock()
        upd.effective_chat.id = chat_id
    return upd


def test_authorized_true_for_matching_chat():
    bot = TelegramCommandBot(bot_token="t", chat_id=42, storage=MagicMock())
    assert bot._authorized(_make_update(42)) is True


def test_authorized_false_for_wrong_chat():
    bot = TelegramCommandBot(bot_token="t", chat_id=42, storage=MagicMock())
    assert bot._authorized(_make_update(99)) is False


def test_authorized_false_when_effective_chat_none():
    bot = TelegramCommandBot(bot_token="t", chat_id=42, storage=MagicMock())
    assert bot._authorized(_make_update(None)) is False
```

- [ ] **Step 2: Run tests — verify FAIL**

Run: `uv run pytest tests/alerts/test_bot_commands.py -v -k authorized`
Expected: FAIL — `ImportError: cannot import name 'TelegramCommandBot'`.

- [ ] **Step 3: Implement the class skeleton**

Append to `src/stake_watch/alerts/bot_commands.py`:

```python
import asyncio
import logging

logger = logging.getLogger(__name__)


class TelegramCommandBot:
    """Long-polling command bot; runs as an asyncio task in main.py."""

    def __init__(self, bot_token: str, chat_id: int, storage):
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._storage = storage
        self._app = None
        self._stopped = asyncio.Event()
        self._shutdown_done = False
        self._protocols_lock = asyncio.Lock()
        self._compare_lock = asyncio.Lock()

    def _authorized(self, update) -> bool:
        chat = getattr(update, "effective_chat", None)
        if chat is None or chat.id != self._chat_id:
            if chat is not None:
                logger.info(
                    "telegram: unauthorized chat_id=%s (expected %s)",
                    chat.id,
                    self._chat_id,
                )
            return False
        return True
```

- [ ] **Step 4: Run tests — verify PASS**

Run: `uv run pytest tests/alerts/test_bot_commands.py -v -k authorized`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stake_watch/alerts/bot_commands.py tests/alerts/test_bot_commands.py
git commit -m "feat(bot-commands): TelegramCommandBot skeleton + _authorized

Class with all handler state (locks, stop event, shutdown flag).
_authorized rejects None effective_chat and mismatched chat_id, and
logs unauthorized attempts at INFO for observability.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 3.2: `_on_help` handler

**Files:**
- Modify: `src/stake_watch/alerts/bot_commands.py`
- Test: `tests/alerts/test_bot_commands.py`

- [ ] **Step 1: Write failing tests**

Append:

```python
import pytest
from unittest.mock import AsyncMock


def _make_update_with_reply(chat_id: int | None, args=None, text=""):
    upd = MagicMock()
    if chat_id is None:
        upd.effective_chat = None
    else:
        upd.effective_chat = MagicMock()
        upd.effective_chat.id = chat_id
    upd.message = MagicMock()
    upd.message.reply_text = AsyncMock()
    upd.message.text = text
    return upd


def _make_context(args=None):
    ctx = MagicMock()
    ctx.args = args or []
    return ctx


@pytest.mark.asyncio
async def test_on_help_authorized_replies_with_help_text():
    bot = TelegramCommandBot("t", 42, MagicMock())
    upd = _make_update_with_reply(42)
    await bot._on_help(upd, _make_context())
    upd.message.reply_text.assert_awaited_once()
    sent = upd.message.reply_text.await_args.args[0]
    assert "/protocols" in sent


@pytest.mark.asyncio
async def test_on_help_unauthorized_silent():
    bot = TelegramCommandBot("t", 42, MagicMock())
    upd = _make_update_with_reply(99)
    await bot._on_help(upd, _make_context())
    upd.message.reply_text.assert_not_awaited()
```

- [ ] **Step 2: Run tests — verify FAIL**

Run: `uv run pytest tests/alerts/test_bot_commands.py -v -k on_help`
Expected: FAIL — `AttributeError: '...' object has no attribute '_on_help'`.

- [ ] **Step 3: Implement `_on_help`**

Add inside the class:

```python
    async def _on_help(self, update, context):
        if not self._authorized(update):
            return
        await update.message.reply_text(format_help())
```

- [ ] **Step 4: Run tests — PASS**

Run: `uv run pytest tests/alerts/test_bot_commands.py -v -k on_help`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stake_watch/alerts/bot_commands.py tests/alerts/test_bot_commands.py
git commit -m "feat(bot-commands): /help handler

Simple pass-through to format_help(); silent for unauthorized chats.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 3.3: `_on_protocols` handler with lock

**Files:**
- Modify: `src/stake_watch/alerts/bot_commands.py`
- Test: `tests/alerts/test_bot_commands.py`

- [ ] **Step 1: Write failing tests**

Append:

```python
@pytest.mark.asyncio
async def test_on_protocols_calls_send_report(monkeypatch):
    bot = TelegramCommandBot("t", 42, MagicMock())
    called = AsyncMock()
    monkeypatch.setattr(
        "stake_watch.alerts.bot_commands.send_protocols_report", called
    )
    upd = _make_update_with_reply(42)
    await bot._on_protocols(upd, _make_context())
    called.assert_awaited_once_with(bot._storage)


@pytest.mark.asyncio
async def test_on_protocols_unauthorized_no_call(monkeypatch):
    bot = TelegramCommandBot("t", 42, MagicMock())
    called = AsyncMock()
    monkeypatch.setattr(
        "stake_watch.alerts.bot_commands.send_protocols_report", called
    )
    upd = _make_update_with_reply(99)
    await bot._on_protocols(upd, _make_context())
    called.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_protocols_replies_wait_when_locked(monkeypatch):
    bot = TelegramCommandBot("t", 42, MagicMock())
    called = AsyncMock()
    monkeypatch.setattr(
        "stake_watch.alerts.bot_commands.send_protocols_report", called
    )
    await bot._protocols_lock.acquire()
    try:
        upd = _make_update_with_reply(42)
        await bot._on_protocols(upd, _make_context())
    finally:
        bot._protocols_lock.release()
    upd.message.reply_text.assert_awaited_once()
    assert "稍等" in upd.message.reply_text.await_args.args[0]
    called.assert_not_awaited()
```

- [ ] **Step 2: Run tests — verify FAIL**

Run: `uv run pytest tests/alerts/test_bot_commands.py -v -k on_protocols`
Expected: FAIL — attribute missing.

- [ ] **Step 3: Implement `_on_protocols`**

At the top of `bot_commands.py` (module level), add the import:

```python
from stake_watch.alerts.protocols_report import send_protocols_report
```

Then inside the class:

```python
    async def _on_protocols(self, update, context):
        if not self._authorized(update):
            return
        if self._protocols_lock.locked():
            await update.message.reply_text("上一个查询还在跑，请稍等…")
            return
        async with self._protocols_lock:
            await send_protocols_report(self._storage)
```

**Important:** the `if self._protocols_lock.locked():` check and the `async with self._protocols_lock:` must be back-to-back with no `await` in between; otherwise you introduce a TOCTOU window. Keep them exactly as written.

- [ ] **Step 4: Run tests — PASS**

Run: `uv run pytest tests/alerts/test_bot_commands.py -v -k on_protocols`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stake_watch/alerts/bot_commands.py tests/alerts/test_bot_commands.py
git commit -m "feat(bot-commands): /protocols handler with concurrency lock

Delegates to send_protocols_report. Serialized by _protocols_lock so
repeat taps don't stack refresh_all_protocols calls; second caller
gets an immediate '稍等' reply instead of queuing.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 3.4: `_on_compare` handler with lock

**Files:**
- Modify: `src/stake_watch/alerts/bot_commands.py`
- Test: `tests/alerts/test_bot_commands.py`

- [ ] **Step 1: Write failing tests**

Append:

```python
@pytest.mark.asyncio
async def test_on_compare_success_no_reply(monkeypatch):
    bot = TelegramCommandBot("t", 42, MagicMock())
    monkeypatch.setattr(
        "stake_watch.alerts.bot_commands.send_comparison_screenshot",
        AsyncMock(return_value={"success": True, "bytes": 1234}),
    )
    upd = _make_update_with_reply(42)
    await bot._on_compare(upd, _make_context())
    upd.message.reply_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_compare_failure_replies_error(monkeypatch):
    bot = TelegramCommandBot("t", 42, MagicMock())
    monkeypatch.setattr(
        "stake_watch.alerts.bot_commands.send_comparison_screenshot",
        AsyncMock(return_value={"success": False, "error": "boom"}),
    )
    upd = _make_update_with_reply(42)
    await bot._on_compare(upd, _make_context())
    upd.message.reply_text.assert_awaited_once()
    assert "boom" in upd.message.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_on_compare_replies_wait_when_locked(monkeypatch):
    bot = TelegramCommandBot("t", 42, MagicMock())
    ss = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(
        "stake_watch.alerts.bot_commands.send_comparison_screenshot", ss
    )
    await bot._compare_lock.acquire()
    try:
        upd = _make_update_with_reply(42)
        await bot._on_compare(upd, _make_context())
    finally:
        bot._compare_lock.release()
    ss.assert_not_awaited()
    upd.message.reply_text.assert_awaited_once()
    assert "稍等" in upd.message.reply_text.await_args.args[0]
```

- [ ] **Step 2: Run tests — verify FAIL**

Run: `uv run pytest tests/alerts/test_bot_commands.py -v -k on_compare`
Expected: FAIL.

- [ ] **Step 3: Implement `_on_compare`**

Add the module-level import:

```python
from stake_watch.alerts.comparison_screenshot import send_comparison_screenshot
```

Add inside the class:

```python
    async def _on_compare(self, update, context):
        if not self._authorized(update):
            return
        if self._compare_lock.locked():
            await update.message.reply_text("上一张截图还在生成，请稍等…")
            return
        async with self._compare_lock:
            result = await send_comparison_screenshot(self._storage)
        if not result.get("success"):
            await update.message.reply_text(
                f"截图失败：{result.get('error') or '未知错误'}"
            )
```

- [ ] **Step 4: Run tests — PASS**

Run: `uv run pytest tests/alerts/test_bot_commands.py -v -k on_compare`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stake_watch/alerts/bot_commands.py tests/alerts/test_bot_commands.py
git commit -m "feat(bot-commands): /compare handler with concurrency lock

Delegates to send_comparison_screenshot; serialized by _compare_lock
to prevent stacking headless-browser sessions. On failure, replies
with the error string so the user sees why.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 3.5: `_on_protocol` handler

**Files:**
- Modify: `src/stake_watch/alerts/bot_commands.py`
- Test: `tests/alerts/test_bot_commands.py`

- [ ] **Step 1: Write failing tests**

Append:

```python
class _FakeProtocolRow:
    def __init__(self, name, chain="Ethereum", enabled=True,
                 safety_score=85, risk_scores=None):
        self.name = name
        self.chain = chain
        self.enabled = enabled
        self.safety_score = safety_score
        self.risk_scores = risk_scores


class _FakeConfigStore:
    def __init__(self, protocols, chains_map=None):
        self._protocols = protocols
        self._chains_map = chains_map or {}

    async def list_protocols(self):
        return self._protocols

    async def get_setting(self, key):
        return self._chains_map.get(key)


class _FakeStorage:
    def __init__(self, session_factory=None, stats=None):
        self._session_factory = session_factory or object()
        self._stats = stats or {}

    async def get_latest_protocol_stats(self, name):
        return self._stats.get(name)


@pytest.mark.asyncio
async def test_on_protocol_no_args_replies_usage(monkeypatch):
    store = _FakeConfigStore([
        _FakeProtocolRow("aave_v3_base"),
        _FakeProtocolRow("morpho_steakhouse_usdc"),
    ])
    monkeypatch.setattr(
        "stake_watch.alerts.bot_commands.ConfigStore", lambda _sf: store
    )
    bot = TelegramCommandBot("t", 42, _FakeStorage())
    upd = _make_update_with_reply(42)
    await bot._on_protocol(upd, _make_context(args=[]))
    sent = upd.message.reply_text.await_args.args[0]
    assert "用法" in sent
    assert "aave_v3_base" in sent and "morpho_steakhouse_usdc" in sent


@pytest.mark.asyncio
async def test_on_protocol_unknown_name_replies_candidates(monkeypatch):
    store = _FakeConfigStore([
        _FakeProtocolRow("aave_v3_base"),
        _FakeProtocolRow("morpho_steakhouse_usdc"),
    ])
    monkeypatch.setattr(
        "stake_watch.alerts.bot_commands.ConfigStore", lambda _sf: store
    )
    bot = TelegramCommandBot("t", 42, _FakeStorage())
    upd = _make_update_with_reply(42)
    await bot._on_protocol(upd, _make_context(args=["nonesuch"]))
    sent = upd.message.reply_text.await_args.args[0]
    assert "未找到" in sent and "nonesuch" in sent
    assert "aave_v3_base" in sent


@pytest.mark.asyncio
async def test_on_protocol_case_insensitive_match(monkeypatch):
    store = _FakeConfigStore([
        _FakeProtocolRow("aave_v3_base"),
        _FakeProtocolRow("kamino_usdc"),
    ])
    monkeypatch.setattr(
        "stake_watch.alerts.bot_commands.ConfigStore", lambda _sf: store
    )
    bot = TelegramCommandBot("t", 42, _FakeStorage())
    upd = _make_update_with_reply(42)
    await bot._on_protocol(upd, _make_context(args=["AAVE_V3_BASE"]))
    sent = upd.message.reply_text.await_args.args[0]
    assert "📋 aave_v3_base" in sent


@pytest.mark.asyncio
async def test_on_protocol_joins_multi_word_args(monkeypatch):
    # Multi-word support is defensive for future protocol names that may
    # contain spaces (e.g. "Aave V3"). Current DB names are single tokens;
    # this test covers the join logic without requiring a shell-quoted arg.
    store = _FakeConfigStore([
        _FakeProtocolRow("Aave V3"),
        _FakeProtocolRow("kamino_usdc"),
    ])
    monkeypatch.setattr(
        "stake_watch.alerts.bot_commands.ConfigStore", lambda _sf: store
    )
    bot = TelegramCommandBot("t", 42, _FakeStorage())
    upd = _make_update_with_reply(42)
    await bot._on_protocol(upd, _make_context(args=["aave", "v3"]))
    sent = upd.message.reply_text.await_args.args[0]
    assert "📋 Aave V3" in sent


@pytest.mark.asyncio
async def test_on_protocol_unauthorized_no_reply(monkeypatch):
    store = _FakeConfigStore([_FakeProtocolRow("aave_v3_base")])
    monkeypatch.setattr(
        "stake_watch.alerts.bot_commands.ConfigStore", lambda _sf: store
    )
    bot = TelegramCommandBot("t", 42, _FakeStorage())
    upd = _make_update_with_reply(99)
    await bot._on_protocol(upd, _make_context(args=["aave_v3_base"]))
    upd.message.reply_text.assert_not_awaited()
```

- [ ] **Step 2: Run tests — verify FAIL**

Run: `uv run pytest tests/alerts/test_bot_commands.py -v -k on_protocol`
Expected: FAIL.

- [ ] **Step 3: Implement `_on_protocol`**

Add the module-level import:

```python
from stake_watch.storage.config_store import ConfigStore
```

Add inside the class:

```python
    async def _on_protocol(self, update, context):
        if not self._authorized(update):
            return

        config_store = ConfigStore(self._storage._session_factory)
        protocols = await config_store.list_protocols()
        candidates = ", ".join(p.name for p in protocols) or "(空)"

        arg = " ".join(context.args or []).strip()
        if not arg:
            await update.message.reply_text(
                f"用法: /protocol <名字>\n可用: {candidates}"
            )
            return

        match = next(
            (p for p in protocols if p.name.lower() == arg.lower()),
            None,
        )
        if match is None:
            await update.message.reply_text(
                f"未找到 '{arg}'。可用: {candidates}"
            )
            return

        chains = await config_store.get_setting(f"protocols.{match.name}.chains")
        stats = await self._storage.get_latest_protocol_stats(match.name)
        tz_offset = await config_store.get_setting("display.timezone_offset") or 8

        text = format_protocol_detail(
            protocol=match,
            chains_breakdown=chains,
            stats=stats,
            tz_offset=int(tz_offset),
        )
        await update.message.reply_text(text)
```

- [ ] **Step 4: Run tests — PASS**

Run: `uv run pytest tests/alerts/test_bot_commands.py -v -k on_protocol`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stake_watch/alerts/bot_commands.py tests/alerts/test_bot_commands.py
git commit -m "feat(bot-commands): /protocol <name> handler

Case-insensitive exact match, multi-word arg join, candidate list on
usage / miss. Pulls chains_breakdown from settings and latest stats
from storage, delegates layout to format_protocol_detail.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 3.6: `_on_error` handler

**Files:**
- Modify: `src/stake_watch/alerts/bot_commands.py`
- Test: `tests/alerts/test_bot_commands.py`

- [ ] **Step 1: Write failing tests**

Append:

```python
@pytest.mark.asyncio
async def test_on_error_replies_to_authorized_chat_and_logs(caplog):
    bot = TelegramCommandBot("t", 42, MagicMock())
    upd = _make_update_with_reply(42)
    ctx = MagicMock()
    ctx.error = RuntimeError("kaboom")
    with caplog.at_level("ERROR", logger="stake_watch.alerts.bot_commands"):
        await bot._on_error(upd, ctx)
    upd.message.reply_text.assert_awaited_once()
    assert "出错" in upd.message.reply_text.await_args.args[0]
    assert any("kaboom" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_on_error_stays_silent_for_unauthorized_chat():
    bot = TelegramCommandBot("t", 42, MagicMock())
    upd = _make_update_with_reply(99)
    ctx = MagicMock()
    ctx.error = RuntimeError("kaboom")
    await bot._on_error(upd, ctx)
    upd.message.reply_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_error_survives_missing_update():
    bot = TelegramCommandBot("t", 42, MagicMock())
    ctx = MagicMock()
    ctx.error = RuntimeError("kaboom")
    # None update happens when the error came from a non-command source.
    await bot._on_error(None, ctx)  # must not raise
```

- [ ] **Step 2: Run tests — verify FAIL**

Run: `uv run pytest tests/alerts/test_bot_commands.py -v -k on_error`
Expected: FAIL.

- [ ] **Step 3: Implement `_on_error`**

Add inside the class:

```python
    async def _on_error(self, update, context):
        logger.error(
            "telegram: handler error: %s",
            getattr(context, "error", None),
            exc_info=getattr(context, "error", None),
        )
        if update is None:
            return
        if not self._authorized(update):
            return
        try:
            await update.message.reply_text("处理命令时出错，请查看服务日志")
        except Exception:  # nosec — reply_text can itself fail
            logger.exception("telegram: failed to notify user of error")
```

- [ ] **Step 4: Run tests — PASS**

Run: `uv run pytest tests/alerts/test_bot_commands.py -v -k on_error`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stake_watch/alerts/bot_commands.py tests/alerts/test_bot_commands.py
git commit -m "feat(bot-commands): error handler

Every handler exception hits _on_error: logs with exc_info, and if
the originating chat was authorized, replies with a generic error
notice. Silent for unauthorized / None updates.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 3.7: `run()` / `stop()` lifecycle

**Files:**
- Modify: `src/stake_watch/alerts/bot_commands.py`
- Test: `tests/alerts/test_bot_commands.py`

- [ ] **Step 1: Write failing tests**

Append:

```python
@pytest.mark.asyncio
async def test_stop_before_start_is_noop_and_sets_event():
    bot = TelegramCommandBot("t", 42, MagicMock())
    await bot.stop()  # no exception
    assert bot._stopped.is_set()


@pytest.mark.asyncio
async def test_stop_is_idempotent(monkeypatch):
    bot = TelegramCommandBot("t", 42, MagicMock())
    # Fake an already-started application
    fake_app = MagicMock()
    fake_app.updater = MagicMock()
    fake_app.updater.running = True
    fake_app.updater.stop = AsyncMock()
    fake_app.running = True
    fake_app.stop = AsyncMock()
    fake_app.shutdown = AsyncMock()
    bot._app = fake_app

    await bot.stop()
    await bot.stop()  # second call must not re-invoke shutdown

    fake_app.updater.stop.assert_awaited_once()
    fake_app.stop.assert_awaited_once()
    fake_app.shutdown.assert_awaited_once()
    assert bot._stopped.is_set()
```

- [ ] **Step 2: Run tests — verify FAIL**

Run: `uv run pytest tests/alerts/test_bot_commands.py -v -k "stop_before or stop_is_idempotent"`
Expected: FAIL — `stop()` not defined.

- [ ] **Step 3: Implement `run` and `stop`**

Add module-level import at the top:

```python
from telegram.ext import ApplicationBuilder, CommandHandler
```

Add inside the class:

```python
    async def run(self):
        self._app = ApplicationBuilder().token(self._bot_token).build()
        self._app.add_handler(CommandHandler("help", self._on_help))
        self._app.add_handler(CommandHandler("protocols", self._on_protocols))
        self._app.add_handler(CommandHandler("compare", self._on_compare))
        self._app.add_handler(CommandHandler("protocol", self._on_protocol))
        self._app.add_error_handler(self._on_error)

        await self._app.initialize()
        try:
            await self._app.bot.set_my_commands([
                ("help", "显示帮助"),
                ("protocols", "全部协议 APY / TVL 概览"),
                ("compare", "协议对比页面截图"),
                ("protocol", "单个协议详情：/protocol <名字>"),
            ])
        except Exception:
            logger.warning("telegram: set_my_commands failed", exc_info=True)

        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        try:
            await self._stopped.wait()
        finally:
            # Best-effort stop in case cancellation reaches us here.
            await self.stop()

    async def stop(self):
        if self._shutdown_done:
            self._stopped.set()
            return
        if self._app is None:
            self._shutdown_done = True
            self._stopped.set()
            return
        self._shutdown_done = True
        try:
            updater = getattr(self._app, "updater", None)
            if updater is not None and getattr(updater, "running", False):
                await updater.stop()
            if getattr(self._app, "running", False):
                await self._app.stop()
            await self._app.shutdown()
        finally:
            self._stopped.set()
```

- [ ] **Step 4: Run all bot_commands tests**

Run: `uv run pytest tests/alerts/test_bot_commands.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stake_watch/alerts/bot_commands.py tests/alerts/test_bot_commands.py
git commit -m "feat(bot-commands): run/stop lifecycle with idempotent shutdown

Manual PTB v22 lifecycle: initialize → set_my_commands →
start → updater.start_polling → wait(_stopped) → stop().

stop() is idempotent (short-circuits on _shutdown_done), safe to
call before start (marks _stopped, returns), and guarded so an
error in set_my_commands does not prevent polling from starting.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 4: Wire into `main.py`

Start the bot as a third asyncio task; stop cleanly on shutdown; parse `chat_id` defensively.

### Task 4.1: Chat_id parsing helper (extracted for testability)

**Files:**
- Modify: `src/stake_watch/alerts/bot_commands.py`
- Test: `tests/alerts/test_bot_commands.py`

- [ ] **Step 1: Write failing tests**

Append:

```python
from stake_watch.alerts.bot_commands import parse_chat_id


@pytest.mark.parametrize("raw,expected", [
    ("42", 42),
    ("  42  ", 42),
    ("-1001234", -1001234),
    (42, 42),
    (None, None),
    ("", None),
    ("   ", None),
    ("abc", None),
    ("42.5", None),
])
def test_parse_chat_id(raw, expected):
    assert parse_chat_id(raw) == expected
```

- [ ] **Step 2: Run test — verify FAIL**

Run: `uv run pytest tests/alerts/test_bot_commands.py -v -k parse_chat_id`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement `parse_chat_id`**

Add module level in `bot_commands.py` (outside the class):

```python
def parse_chat_id(raw) -> int | None:
    """Best-effort convert a stored chat_id setting to int; None on garbage."""
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    # int() accepts leading '-' (channels use negative IDs); refuse floats/text.
    try:
        return int(s)
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 4: Run test — PASS**

Run: `uv run pytest tests/alerts/test_bot_commands.py -v -k parse_chat_id`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stake_watch/alerts/bot_commands.py tests/alerts/test_bot_commands.py
git commit -m "feat(bot-commands): parse_chat_id helper

Extract the chat_id parsing that main.py needs. Handles int passthrough,
strips whitespace, refuses empty / non-integer input. Channel IDs are
negative so we allow leading '-'.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 4.2: Start bot from `main.py`

**Files:**
- Modify: `src/stake_watch/main.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Read the current test_main.py for context**

Run: `cat tests/test_main.py`
Observe the existing style — some tests may mock the storage/config_store; follow the same conventions.

- [ ] **Step 2: Write failing tests for `_build_command_bot`**

The bot startup logic is behavioral (creates a task, cleans up on shutdown). To keep tests small and fast, `main.py` extracts a factory `_build_command_bot(bot_token, chat_id_raw, storage) -> TelegramCommandBot | None` — tested here. The actual `create_task` / `_safe_run_bot` / ordered shutdown wiring is covered by the manual smoke test in Task 5.2 (documented gap: full main() startup is too integration-y to unit-test without heavy mocking).

Append to `tests/test_main.py`:

```python
import pytest
from unittest.mock import MagicMock


@pytest.mark.asyncio
async def test_build_command_bot_returns_bot_when_config_present():
    from stake_watch.main import _build_command_bot
    storage = MagicMock()
    bot = _build_command_bot("fake-token", "42", storage)
    assert bot is not None
    assert bot._bot_token == "fake-token"
    assert bot._chat_id == 42


@pytest.mark.asyncio
async def test_build_command_bot_returns_none_when_token_missing():
    from stake_watch.main import _build_command_bot
    assert _build_command_bot(None, "42", MagicMock()) is None
    assert _build_command_bot("", "42", MagicMock()) is None


@pytest.mark.asyncio
async def test_build_command_bot_returns_none_when_chat_id_missing_or_invalid():
    from stake_watch.main import _build_command_bot
    assert _build_command_bot("t", None, MagicMock()) is None
    assert _build_command_bot("t", "abc", MagicMock()) is None
    assert _build_command_bot("t", "", MagicMock()) is None
```

- [ ] **Step 3: Run tests — verify FAIL**

Run: `uv run pytest tests/test_main.py -v -k build_command_bot`
Expected: FAIL — `ImportError: cannot import name '_build_command_bot'`.

- [ ] **Step 4: Add `_build_command_bot` in `main.py` and wire it up**

At the top of `src/stake_watch/main.py`, add:

```python
from stake_watch.alerts.bot_commands import TelegramCommandBot, parse_chat_id
```

Add this factory near the top of the file (module scope, above `build_app`):

```python
def _build_command_bot(bot_token, chat_id_raw, storage) -> TelegramCommandBot | None:
    """Return a TelegramCommandBot if config is present and valid, else None."""
    if not bot_token:
        return None
    chat_id = parse_chat_id(chat_id_raw)
    if chat_id is None:
        logger.warning("Invalid or missing telegram.chat_id %r; bot commands disabled",
                       chat_id_raw)
        return None
    return TelegramCommandBot(bot_token, chat_id, storage)
```

Then inside `main()`, after `scheduled.start()` and before `import uvicorn`, add:

```python
    # Interactive Telegram command bot (optional).
    command_bot = _build_command_bot(
        await config_store.get_setting("telegram.bot_token"),
        await config_store.get_setting("telegram.chat_id"),
        storage,
    )
    bot_task = None
    if command_bot is not None:
        async def _safe_run_bot():
            try:
                await command_bot.run()
            except Exception:
                logger.exception("Telegram command bot crashed")
            finally:
                await command_bot.stop()

        bot_task = asyncio.create_task(_safe_run_bot())
        logger.info("Telegram command bot started")
```

Modify the `finally` block at the end of `main()`:

```python
    try:
        await server.serve()
    finally:
        if command_bot is not None:
            await command_bot.stop()
        if bot_task is not None:
            try:
                await bot_task
            except asyncio.CancelledError:
                pass  # normal shutdown path
            except Exception:
                logger.exception("Telegram command bot task raised on shutdown")
        scheduled.stop()
        await storage.close()
```

Order matters: stop the bot before the scheduler / storage so any in-flight handler that touches storage has already returned. `CancelledError` is caught explicitly because if the outer task is cancelled during shutdown, `await bot_task` re-raises it; letting it propagate would skip `scheduled.stop()` / `storage.close()`.

- [ ] **Step 5: Run tests — PASS**

Run: `uv run pytest tests/test_main.py -v -k build_command_bot`
Expected: PASS.

- [ ] **Step 6: Run the full test suite as a sanity check**

Run: `uv run pytest tests/ -v`
Expected: All tests pass, including the pre-existing 392.

- [ ] **Step 7: Commit**

```bash
git add src/stake_watch/main.py tests/test_main.py
git commit -m "feat(main): start Telegram command bot alongside API + scheduler

Auto-enabled when telegram.bot_token and telegram.chat_id are both
set. Runs as a third asyncio task; stops cleanly before scheduler
and storage on shutdown. Invalid chat_id logs a warning and skips.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 5: Manual verification + coverage check

Automation covers the seams; this chunk locks in that the whole thing actually works end-to-end.

### Task 5.1: Coverage report

**Files:** none (read-only check)

- [ ] **Step 1: Run coverage on the new module**

Run: `uv run pytest tests/alerts/test_bot_commands.py --cov=stake_watch.alerts.bot_commands --cov-report=term-missing`
Expected: coverage ≥ 80%. If under, add tests for the uncovered branches — do not silence with `# pragma: no cover`.

- [ ] **Step 2: Run full suite with coverage**

Run: `uv run pytest tests/ --cov=stake_watch --cov-report=term`
Expected: All 392 + new tests PASS; overall coverage steady or improved.

### Task 5.2: Live smoke test (only if you have a real Telegram bot token)

**Files:** none

- [ ] **Step 1: Confirm DB has `telegram.bot_token` and `telegram.chat_id`**

Run:

```bash
uv run python <<'PY'
import asyncio
from stake_watch.storage.db import Storage
from stake_watch.storage.config_store import ConfigStore

async def go():
    s = Storage('sqlite+aiosqlite:///stake_watch.db')
    await s.initialize()
    c = ConfigStore(s._session_factory)
    print('token set:', bool(await c.get_setting('telegram.bot_token')))
    print('chat_id:', await c.get_setting('telegram.chat_id'))
    await s.close()

asyncio.run(go())
PY
```

If either is empty, set them from the frontend Settings page before continuing.

- [ ] **Step 2: Start the backend**

Run: `uv run python -m stake_watch.main`
Expected log line: `Telegram command bot started` shortly after `Stake Watch started with N collectors, ...`.

- [ ] **Step 3: In Telegram, send `/help` to your bot**

Expected: reply lists all four commands.

- [ ] **Step 4: Send `/protocols`**

Expected: within a few seconds you get the scheduled-report-style message (whatever `send_protocols_report` normally sends).

- [ ] **Step 5: Send `/compare`**

Expected: within ~30 s (Playwright warm-up) you get the comparison-page screenshot.

- [ ] **Step 6: Send `/protocol <a-name-from-your-DB>`**

Pick any protocol you have configured (e.g. `/protocol aave_v3_base` — use `list_protocols()` values, not display names).
Expected: the single-protocol detail message with layout matching the spec.

- [ ] **Step 7: Send `/protocol nonesuch`**

Expected: "未找到 'nonesuch'。可用: <comma-separated list of your configured protocols>"

- [ ] **Step 8: Ctrl-C the backend**

Expected: clean shutdown, no "Task was destroyed but it is pending" warnings for the bot task.

- [ ] **Step 9: Commit anything you had to fix during smoke testing**

If you found issues, write a new test that would have caught them first, then fix. Then commit both.

```bash
git add <files>
git commit -m "fix(bot-commands): <specific issue found in smoke test>

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Done Criteria

- [ ] `uv run pytest tests/ -v` — all pre-existing tests still pass, plus all new bot_commands tests
- [ ] `uv run pytest --cov=stake_watch.alerts.bot_commands` shows ≥ 80% coverage
- [ ] Backend starts and logs "Telegram command bot started" (given valid config)
- [ ] All four commands respond correctly from the configured chat
- [ ] Messages from an unrelated chat_id are silently ignored (no reply)
- [ ] Clean shutdown on Ctrl-C — no pending-task warnings

## References

- Spec: `docs/superpowers/specs/2026-07-03-telegram-bot-commands-design.md`
- TDD workflow: `docs/testing/tdd.md`
- Commit conventions: `docs/git/commits.md`
- Existing pattern for scheduled Telegram sends: `src/stake_watch/alerts/protocols_report.py`, `src/stake_watch/alerts/comparison_screenshot.py`
- python-telegram-bot v22 Application lifecycle: https://docs.python-telegram-bot.org/en/v22.8/telegram.ext.application.html
