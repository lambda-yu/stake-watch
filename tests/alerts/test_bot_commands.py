"""Tests for the interactive Telegram command bot."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from stake_watch.alerts.bot_commands import (
    TelegramCommandBot,
    format_help,
    format_protocol_detail,
)


# ---------- format_help ----------

def test_format_help_lists_all_four_commands():
    text = format_help()
    for cmd in ("/help", "/protocols", "/compare", "/protocol <"):
        assert cmd in text, f"missing {cmd} in help output"


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
    # Order semantics: USDC before USDT, primary chain (Ethereum) before Base
    assert out.index("USDC") < out.index("USDT")
    assert out.index("Ethereum") < out.index("Base")


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


class _FakeProtocolRow:
    def __init__(self, name, chain="ethereum", enabled=True,
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
