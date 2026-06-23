"""Tests for on-chain signal readers (Chainlink/Sequencer/Solana/Pyth)."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from stake_watch.risk import onchain_signals
from stake_watch.risk.onchain_signals import (
    CHAINLINK_FEEDS,
    DEFAULT_HEARTBEAT,
    PYTH_FEED_IDS,
    SEQUENCER_FEEDS,
    _eth_call,
    _parse_latest_round_data,
    fetch_chainlink_price,
    fetch_pyth_price,
    fetch_sequencer_status,
    fetch_solana_health,
)


# ---------- _parse_latest_round_data ----------

def _encode_round(answer: int, started_at: int, updated_at: int,
                  round_id: int = 1, answered_in: int = 1) -> str:
    vals = [round_id, answer, started_at, updated_at, answered_in]
    # int256 two's-complement for negative values
    parts = [f"{(v & ((1 << 256) - 1)):064x}" for v in vals]
    return "0x" + "".join(parts)


def test_parse_returns_none_for_short_payload():
    assert _parse_latest_round_data("0x" + "00" * 10) is None


def test_parse_returns_none_for_empty():
    assert _parse_latest_round_data("") is None


def test_parse_returns_none_for_non_hex():
    assert _parse_latest_round_data("not-a-hex-string") is None


def test_parse_extracts_round_fields():
    now = int(time.time())
    payload = _encode_round(answer=100_000_000, started_at=now - 60, updated_at=now - 30)
    answer, started, updated, age = _parse_latest_round_data(payload)
    assert answer == 100_000_000
    assert started == now - 60
    assert updated == now - 30
    assert 28 <= age <= 32  # allow tiny clock drift


def test_parse_handles_negative_int256():
    payload = _encode_round(answer=-1, started_at=0, updated_at=0)
    answer, *_ = _parse_latest_round_data(payload)
    assert answer == -1


def test_parse_zero_answer_for_sequencer_up():
    now = int(time.time())
    payload = _encode_round(answer=0, started_at=now - 3600, updated_at=now)
    answer, started, _, _ = _parse_latest_round_data(payload)
    assert answer == 0
    assert started == now - 3600


# ---------- _eth_call ----------

class _MockResponse:
    def __init__(self, json_data, status=200):
        self._json = json_data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)

    def json(self):
        return self._json


def _patch_httpx(response_json=None, raise_exc=None):
    """Helper: patch AsyncClient.post / .get to return the given response."""
    client = MagicMock()
    if raise_exc:
        client.post = AsyncMock(side_effect=raise_exc)
        client.get = AsyncMock(side_effect=raise_exc)
    else:
        client.post = AsyncMock(return_value=_MockResponse(response_json))
        client.get = AsyncMock(return_value=_MockResponse(response_json))
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("httpx.AsyncClient", return_value=ctx)


@pytest.mark.asyncio
async def test_eth_call_returns_result_field():
    with _patch_httpx({"result": "0xdeadbeef"}):
        out = await _eth_call("https://rpc", "0xabc", "0xfeaf968c")
    assert out == "0xdeadbeef"


@pytest.mark.asyncio
async def test_eth_call_returns_none_on_exception():
    with _patch_httpx(raise_exc=httpx.ConnectError("boom")):
        out = await _eth_call("https://rpc", "0xabc", "0xfeaf968c")
    assert out is None


# ---------- fetch_chainlink_price ----------

@pytest.mark.asyncio
async def test_chainlink_returns_none_for_unknown_pair():
    out = await fetch_chainlink_price("https://rpc", "polygon", "DAI")
    assert out is None


@pytest.mark.asyncio
async def test_chainlink_returns_none_when_eth_call_fails():
    with _patch_httpx(raise_exc=httpx.ConnectError("boom")):
        out = await fetch_chainlink_price("https://rpc", "ethereum", "USDC")
    assert out is None


@pytest.mark.asyncio
async def test_chainlink_returns_none_for_garbage_payload():
    with _patch_httpx({"result": "0x00"}):
        out = await fetch_chainlink_price("https://rpc", "ethereum", "USDC")
    assert out is None


@pytest.mark.asyncio
async def test_chainlink_returns_price_and_freshness_flags():
    now = int(time.time())
    payload = _encode_round(answer=100_000_000, started_at=now - 60, updated_at=now - 60)
    with _patch_httpx({"result": payload}):
        out = await fetch_chainlink_price("https://rpc", "ethereum", "USDC")
    assert out["price"] == 1.0
    assert out["heartbeat_seconds"] == DEFAULT_HEARTBEAT
    assert out["is_stale"] is False
    assert out["feed_address"] == CHAINLINK_FEEDS[("ethereum", "USDC")]


@pytest.mark.asyncio
async def test_chainlink_stale_when_age_exceeds_heartbeat_x_1_1():
    now = int(time.time())
    stale = now - int(DEFAULT_HEARTBEAT * 1.2)
    payload = _encode_round(answer=100_000_000, started_at=stale, updated_at=stale)
    with _patch_httpx({"result": payload}):
        out = await fetch_chainlink_price("https://rpc", "ethereum", "USDC")
    assert out["is_stale"] is True


# ---------- fetch_sequencer_status ----------

@pytest.mark.asyncio
async def test_sequencer_returns_none_for_unknown_chain():
    out = await fetch_sequencer_status("https://rpc", "ethereum")
    assert out is None


@pytest.mark.asyncio
async def test_sequencer_up_when_answer_zero():
    now = int(time.time())
    payload = _encode_round(answer=0, started_at=now - 7200, updated_at=now - 60)
    with _patch_httpx({"result": payload}):
        out = await fetch_sequencer_status("https://rpc", "base")
    assert out["is_up"] is True
    assert out["seconds_in_status"] >= 7200
    assert SEQUENCER_FEEDS["base"]


@pytest.mark.asyncio
async def test_sequencer_down_when_answer_nonzero():
    now = int(time.time())
    payload = _encode_round(answer=1, started_at=now - 300, updated_at=now)
    with _patch_httpx({"result": payload}):
        out = await fetch_sequencer_status("https://rpc", "base")
    assert out["is_up"] is False
    assert "status_since_dt" in out


@pytest.mark.asyncio
async def test_sequencer_returns_none_on_parse_failure():
    with _patch_httpx({"result": "0x00"}):
        out = await fetch_sequencer_status("https://rpc", "base")
    assert out is None


# ---------- fetch_solana_health ----------

@pytest.mark.asyncio
async def test_solana_health_computes_slot_rate_and_tps():
    samples = [
        {"numSlots": 150, "samplePeriodSecs": 60,
         "numNonVoteTransactions": 6000, "slot": 1000},
        {"numSlots": 150, "samplePeriodSecs": 60,
         "numNonVoteTransactions": 6000, "slot": 999},
    ]
    with _patch_httpx({"result": samples}):
        out = await fetch_solana_health("https://rpc")
    assert out["slot_rate"] == pytest.approx(2.5)
    assert out["tps_non_vote"] == pytest.approx(100.0)
    assert out["latest_slot"] == 1000
    assert out["samples"] == 2
    assert out["degraded"] is False
    assert out["critical"] is False


@pytest.mark.asyncio
async def test_solana_health_flags_degraded_below_2():
    samples = [{"numSlots": 100, "samplePeriodSecs": 60,
                "numNonVoteTransactions": 0, "slot": 1}]
    with _patch_httpx({"result": samples}):
        out = await fetch_solana_health("https://rpc")
    # slot_rate = 100/60 ≈ 1.67
    assert out["degraded"] is True
    assert out["critical"] is False


@pytest.mark.asyncio
async def test_solana_health_flags_critical_below_1_5():
    samples = [{"numSlots": 60, "samplePeriodSecs": 60,
                "numNonVoteTransactions": 0, "slot": 1}]
    with _patch_httpx({"result": samples}):
        out = await fetch_solana_health("https://rpc")
    assert out["critical"] is True
    assert out["degraded"] is True


@pytest.mark.asyncio
async def test_solana_health_returns_none_for_empty_samples():
    with _patch_httpx({"result": []}):
        out = await fetch_solana_health("https://rpc")
    assert out is None


@pytest.mark.asyncio
async def test_solana_health_returns_none_on_zero_period():
    samples = [{"numSlots": 100, "samplePeriodSecs": 0,
                "numNonVoteTransactions": 0, "slot": 1}]
    with _patch_httpx({"result": samples}):
        out = await fetch_solana_health("https://rpc")
    assert out is None


@pytest.mark.asyncio
async def test_solana_health_returns_none_on_exception():
    with _patch_httpx(raise_exc=httpx.ConnectError("boom")):
        out = await fetch_solana_health("https://rpc")
    assert out is None


# ---------- fetch_pyth_price ----------

@pytest.mark.asyncio
async def test_pyth_returns_none_for_unknown_assets():
    out = await fetch_pyth_price(["NEVER_SEEN"])
    assert out is None


@pytest.mark.asyncio
async def test_pyth_returns_prices_per_asset():
    now = int(time.time())
    response = {"parsed": [
        {"id": PYTH_FEED_IDS["USDC"],
         "price": {"price": "100000000", "expo": "-8", "publish_time": now - 5}},
        {"id": PYTH_FEED_IDS["USDT"],
         "price": {"price": "99980000", "expo": "-8", "publish_time": now - 10}},
    ]}
    with _patch_httpx(response):
        out = await fetch_pyth_price(["USDC", "USDT"])
    assert out["USDC"]["price"] == pytest.approx(1.0)
    assert out["USDT"]["price"] == pytest.approx(0.9998)
    assert 4 <= out["USDC"]["age_seconds"] <= 6
    assert 9 <= out["USDT"]["age_seconds"] <= 11


@pytest.mark.asyncio
async def test_pyth_tolerates_0x_prefixed_ids_in_response():
    now = int(time.time())
    response = {"parsed": [
        {"id": "0x" + PYTH_FEED_IDS["USDC"],
         "price": {"price": "100000000", "expo": "-8", "publish_time": now}},
    ]}
    with _patch_httpx(response):
        out = await fetch_pyth_price(["USDC"])
    assert "USDC" in out


@pytest.mark.asyncio
async def test_pyth_returns_none_on_exception():
    with _patch_httpx(raise_exc=httpx.ConnectError("boom")):
        out = await fetch_pyth_price(["USDC"])
    assert out is None


@pytest.mark.asyncio
async def test_pyth_skips_malformed_entries():
    response = {"parsed": [
        {"id": PYTH_FEED_IDS["USDC"], "price": {"expo": "-8"}},  # missing price
    ]}
    with _patch_httpx(response):
        out = await fetch_pyth_price(["USDC"])
    assert out is None
