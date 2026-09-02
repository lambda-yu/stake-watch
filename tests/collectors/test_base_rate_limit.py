"""Tests for the BaseCollector rate-limit retry + per-chain concurrency cap."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest

from stake_watch.collectors.base import (
    BaseCollector,
    _get_chain_semaphore,
    _looks_like_rate_limit,
)
from stake_watch.models.common import Chain
from stake_watch.models.protocol import ProtocolStats


class _Stub(BaseCollector):
    """Test collector whose collect_protocol_stats can be programmed to
    fail a given number of times before succeeding."""
    _rate_limit_base_delay = 0.01  # keep tests fast

    def __init__(self, chain=Chain.BASE, *, fail_times=0, exc=None):
        super().__init__(chain=chain, protocol="stub")
        self.fail_times = fail_times
        self.calls = 0
        self.exc = exc or Exception("429 Too Many Requests")

    async def collect_positions(self, wallet):
        return []

    async def collect_protocol_stats(self):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc
        return ProtocolStats(chain=self.chain, protocol=self.protocol,
                              tvl_usd=Decimal("0"), pools=[],
                              updated_at=datetime.now(timezone.utc))


# ---------- _looks_like_rate_limit ----------

@pytest.mark.parametrize("msg,expected", [
    ("429 Too Many Requests", True),
    ("rate limit exceeded", True),
    ("HTTP 429", True),
    ("connection reset", False),
    ("timeout", False),
    ("500 Internal Server Error", False),
])
def test_looks_like_rate_limit_classifier(msg, expected):
    assert _looks_like_rate_limit(Exception(msg)) is expected


# ---------- retry behaviour ----------

@pytest.mark.asyncio
async def test_retries_on_429_then_succeeds():
    c = _Stub(fail_times=2)  # third call succeeds
    result = await c.collect("")
    assert c.calls == 3
    assert result.protocol_stats is not None
    assert result.errors == []


@pytest.mark.asyncio
async def test_gives_up_after_all_retries_exhausted():
    c = _Stub(fail_times=99)  # never succeeds
    result = await c.collect("")
    assert c.calls == 3  # default _rate_limit_retries
    assert result.protocol_stats is None
    assert len(result.errors) == 1
    assert "429" in result.errors[0]


@pytest.mark.asyncio
async def test_non_ratelimit_error_does_not_retry():
    c = _Stub(fail_times=1, exc=ValueError("bad input"))
    result = await c.collect("")
    assert c.calls == 1  # no retry
    assert result.protocol_stats is None


@pytest.mark.asyncio
async def test_retries_on_transient_network_error_then_succeeds():
    c = _Stub(fail_times=2, exc=httpx.ConnectTimeout("connect timed out"))
    result = await c.collect("")
    assert c.calls == 3
    assert result.protocol_stats is not None
    assert result.errors == []


# ---------- per-chain semaphore ----------

@pytest.mark.asyncio
async def test_base_chain_semaphore_limits_to_one_concurrent():
    """Two Base collectors started together should NOT run stats overlap;
    the second must wait for the first to release."""
    started_events = []
    finish_lock = asyncio.Event()

    class _Sleepy(BaseCollector):
        def __init__(self, tag):
            super().__init__(chain=Chain.BASE, protocol=tag)
            self.tag = tag

        async def collect_positions(self, wallet):
            return []

        async def collect_protocol_stats(self):
            started_events.append((self.tag, "start"))
            await finish_lock.wait()
            started_events.append((self.tag, "end"))
            return ProtocolStats(chain=self.chain, protocol=self.protocol,
                                   tvl_usd=Decimal("0"), pools=[],
                                   updated_at=datetime.now(timezone.utc))

    # Fresh semaphore
    from stake_watch.collectors import base as base_mod
    base_mod._chain_semaphores.clear()

    a, b = _Sleepy("a"), _Sleepy("b")
    t_a = asyncio.create_task(a.collect(""))
    t_b = asyncio.create_task(b.collect(""))

    # Let A grab semaphore + start
    await asyncio.sleep(0.05)
    # Only one should have started so far
    starts = [e for e in started_events if e[1] == "start"]
    assert len(starts) == 1

    finish_lock.set()
    await asyncio.gather(t_a, t_b)

    # Both eventually ran to completion
    assert len([e for e in started_events if e[1] == "start"]) == 2
    assert len([e for e in started_events if e[1] == "end"]) == 2


def test_get_chain_semaphore_creates_per_chain_singletons():
    from stake_watch.collectors import base as base_mod
    base_mod._chain_semaphores.clear()
    s1 = _get_chain_semaphore(Chain.BASE)
    s2 = _get_chain_semaphore(Chain.BASE)
    s3 = _get_chain_semaphore(Chain.ETHEREUM)
    assert s1 is s2
    assert s1 is not s3
