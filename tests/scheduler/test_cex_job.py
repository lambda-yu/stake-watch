import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone
from stake_watch.storage.db import Storage
from stake_watch.storage.config_store import ConfigStore
from stake_watch.models.cex import CexVenue, CexEarnRate, VenueRateSnapshot
from stake_watch.scheduler.runner import ScheduledRunner, CollectionRunner


@pytest.fixture
async def wired():
    s = Storage("sqlite+aiosqlite:///:memory:")
    await s.initialize()
    store = ConfigStore(s._session_factory)
    await store.upsert_cex_venue(CexVenue(name="okx", display_name="OKX"))
    await store.upsert_cex_venue(CexVenue(name="binance", display_name="Binance"))
    # CollectionRunner is required by ScheduledRunner but never touched by
    # _refresh_cex_rates — pass a bare-minimum instance.
    cr = CollectionRunner(collectors=[], storage=s, wallets=[])
    runner = ScheduledRunner(collection_runner=cr, storage=s, cex_rates_interval=1)
    yield runner, s, store
    await s.close()


@pytest.mark.asyncio
async def test_refresh_writes_rates_and_swallows_errors(wired):
    runner, s, store = wired
    now = datetime.now(timezone.utc)
    okx_ok = VenueRateSnapshot(venue="okx", rates=[
        CexEarnRate(venue="okx", asset="USDT", apy_min=0.04, apy_max=0.04,
                    updated_at=now)])
    binance_fail = VenueRateSnapshot(venue="binance", rates=[], errors=["boom"])

    def _fake_build(v):
        m = AsyncMock()
        m.collect = AsyncMock(return_value=okx_ok if v.name == "okx" else binance_fail)
        return m

    # Patch target must be the name lookup at call time (module-top import).
    with patch("stake_watch.scheduler.runner.build_cex_collector", side_effect=_fake_build):
        await runner._refresh_cex_rates()

    latest = await s.list_latest_cex_rates()
    assert len(latest) == 1 and latest[0].venue == "okx"