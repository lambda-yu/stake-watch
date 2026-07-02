"""Tests for CollectionRunner.run_collection_cycle: parallel + timeout."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from stake_watch.collectors.base import BaseCollector, CollectResult
from stake_watch.models.common import Chain
from stake_watch.models.protocol import ProtocolStats
from stake_watch.scheduler.runner import CollectionRunner


def _fake_storage():
    s = MagicMock()
    s.save_protocol_stats = AsyncMock()
    s.save_positions = AsyncMock()
    return s


class _SlowCollector(BaseCollector):
    def __init__(self, protocol, delay, chain=Chain.BASE):
        super().__init__(chain=chain, protocol=protocol)
        self.delay = delay
        self.finished = False

    async def collect_positions(self, wallet):
        return []

    async def collect_protocol_stats(self):
        await asyncio.sleep(self.delay)
        self.finished = True
        return ProtocolStats(chain=self.chain, protocol=self.protocol,
                              tvl_usd=Decimal("0"), pools=[],
                              updated_at=datetime.now(timezone.utc))


class _HangingCollector(BaseCollector):
    """Simulates a stuck RPC — never returns from collect_protocol_stats."""
    async def collect_positions(self, wallet):
        return []

    async def collect_protocol_stats(self):
        await asyncio.sleep(3600)  # would hang for an hour
        raise RuntimeError("should never reach here")


@pytest.mark.asyncio
async def test_different_chain_collectors_run_in_parallel():
    """Two collectors on different chains should run concurrently:
    total time ≈ max(delays) not sum(delays)."""
    from stake_watch.collectors import base as base_mod
    base_mod._chain_semaphores.clear()

    a = _SlowCollector("a", delay=0.4, chain=Chain.BASE)
    b = _SlowCollector("b", delay=0.4, chain=Chain.ETHEREUM)
    runner = CollectionRunner(collectors=[a, b], storage=_fake_storage(), wallets=[""])
    start = time.monotonic()
    results = await runner.run_collection_cycle()
    elapsed = time.monotonic() - start
    # Parallel: ~0.4s. Sequential would be ~0.8s. Give some slack.
    assert elapsed < 0.7, f"expected parallel execution, took {elapsed:.2f}s"
    assert all(r.protocol_stats is not None for r in results)


@pytest.mark.asyncio
async def test_same_chain_collectors_serialise_via_semaphore():
    """Two Base collectors: semaphore=1 forces serial → total ~ sum(delays)."""
    from stake_watch.collectors import base as base_mod
    base_mod._chain_semaphores.clear()

    a = _SlowCollector("a", delay=0.3, chain=Chain.BASE)
    b = _SlowCollector("b", delay=0.3, chain=Chain.BASE)
    runner = CollectionRunner(collectors=[a, b], storage=_fake_storage(), wallets=[""])
    start = time.monotonic()
    await runner.run_collection_cycle()
    elapsed = time.monotonic() - start
    # Sum ≈ 0.6s. Parallel would be ~0.3s.
    assert elapsed >= 0.55, f"expected serial via Base semaphore, took {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_hanging_collector_kills_only_itself_at_timeout():
    """A stuck collector must not block the others — the wait_for cap fires
    and the other collectors' results are preserved."""
    from stake_watch.collectors import base as base_mod
    from stake_watch.scheduler import runner as runner_mod
    base_mod._chain_semaphores.clear()

    # Shrink timeout for the test
    original = runner_mod.CollectionRunner.PER_COLLECTOR_TIMEOUT
    runner_mod.CollectionRunner.PER_COLLECTOR_TIMEOUT = 0.5

    hang = _HangingCollector(chain=Chain.ETHEREUM, protocol="hang")
    fast = _SlowCollector("fast", delay=0.1, chain=Chain.SOLANA)
    try:
        runner = CollectionRunner(collectors=[hang, fast], storage=_fake_storage(),
                                    wallets=[""])
        start = time.monotonic()
        results = await runner.run_collection_cycle()
        elapsed = time.monotonic() - start
    finally:
        runner_mod.CollectionRunner.PER_COLLECTOR_TIMEOUT = original

    # Should complete in ~0.5s (the timeout cap), NOT 3600s
    assert elapsed < 1.5

    hang_result = next(r for r in results if r.errors and "hang" in r.errors[0])
    assert "timed out" in hang_result.errors[0]

    fast_result = next(r for r in results if r.protocol_stats
                        and r.protocol_stats.protocol == "fast")
    assert fast_result.protocol_stats is not None


@pytest.mark.asyncio
async def test_empty_collectors_list_returns_empty():
    runner = CollectionRunner(collectors=[], storage=_fake_storage(), wallets=[""])
    results = await runner.run_collection_cycle()
    assert results == []
