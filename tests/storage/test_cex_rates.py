import pytest
from datetime import datetime, timezone, timedelta
from stake_watch.storage.db import Storage
from stake_watch.models.cex import CexEarnRate


@pytest.fixture
async def storage():
    s = Storage("sqlite+aiosqlite:///:memory:")
    await s.initialize()
    yield s
    await s.close()


def _rate(venue, asset, apy_min, apy_max, updated_at):
    return CexEarnRate(venue=venue, asset=asset, apy_min=apy_min,
                       apy_max=apy_max, updated_at=updated_at)


@pytest.mark.asyncio
async def test_insert_and_latest(storage):
    now = datetime.now(timezone.utc)
    older = now - timedelta(minutes=30)
    await storage.insert_cex_rates([
        _rate("okx", "USDT", 0.03, 0.03, older),
        _rate("okx", "USDT", 0.04, 0.05, now),
    ])
    rows = await storage.list_latest_cex_rates()
    assert len(rows) == 1
    assert rows[0].apy_min == 0.04 and rows[0].apy_max == 0.05


@pytest.mark.asyncio
async def test_history_filter(storage):
    now = datetime.now(timezone.utc)
    await storage.insert_cex_rates([
        _rate("okx", "USDT", 0.03, 0.03, now - timedelta(hours=2)),
        _rate("okx", "USDT", 0.04, 0.04, now - timedelta(hours=1)),
        _rate("okx", "USDT", 0.05, 0.05, now),
        _rate("binance", "USDT", 0.06, 0.06, now),
    ])
    rows = await storage.list_cex_history(venue="okx", asset="USDT",
        since=now - timedelta(hours=90/60), limit=10)
    # since = now - 1.5h, so first entry (2h ago) is excluded
    assert len(rows) == 2
    assert all(r.venue == "okx" for r in rows)