import pytest
from datetime import datetime, timezone
from stake_watch.collectors.cex.base import CexEarnCollector
from stake_watch.models.cex import CexEarnRate


class _FlakyThenOk(CexEarnCollector):
    venue = "flaky"
    _base_delay = 0.01  # fast tests

    def __init__(self):
        super().__init__(assets=["USDT"])
        self.calls = 0

    async def fetch(self):
        self.calls += 1
        if self.calls < 3:
            raise RuntimeError("429 too many requests")
        return [CexEarnRate(venue="flaky", asset="USDT",
                            apy_min=0.05, apy_max=0.05,
                            updated_at=datetime.now(timezone.utc))]


class _AlwaysBroken(CexEarnCollector):
    venue = "broken"
    _base_delay = 0.01

    def __init__(self):
        super().__init__(assets=["USDT"])

    async def fetch(self):
        raise RuntimeError("500 server error")


class _NotRateLimit(CexEarnCollector):
    venue = "hard"
    _base_delay = 0.01

    def __init__(self):
        super().__init__(assets=["USDT"])
        self.calls = 0

    async def fetch(self):
        self.calls += 1
        raise ValueError("bad JSON")


@pytest.mark.asyncio
async def test_retries_on_429_then_succeeds():
    c = _FlakyThenOk()
    snap = await c.collect()
    assert snap.errors == [] and len(snap.rates) == 1
    assert c.calls == 3


@pytest.mark.asyncio
async def test_500_lands_in_errors():
    snap = await _AlwaysBroken().collect()
    assert snap.rates == [] and len(snap.errors) == 1
    assert "500" in snap.errors[0]


@pytest.mark.asyncio
async def test_non_rate_limit_does_not_retry():
    c = _NotRateLimit()
    snap = await c.collect()
    assert snap.rates == [] and c.calls == 1
    assert "bad JSON" in snap.errors[0]