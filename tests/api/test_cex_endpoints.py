import pytest
from datetime import datetime, timezone
from httpx import ASGITransport, AsyncClient
from stake_watch.api.app import create_app
from stake_watch.api.deps import get_config_store
from stake_watch.models.cex import CexVenue, CexEarnRate
from stake_watch.storage.db import Storage


@pytest.fixture
async def app_ctx(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    storage = Storage(db_url)
    await storage.initialize()
    app = create_app(storage)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, storage, get_config_store()
    await storage.close()


@pytest.mark.asyncio
async def test_list_venues_returns_upserted(app_ctx):
    client, _storage, store = app_ctx
    await store.upsert_cex_venue(CexVenue(name="okx", display_name="OKX"))
    r = await client.get("/api/cex/venues")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1 and body[0]["name"] == "okx"
    assert body[0]["assets"] == ["USDT", "USDC"]


@pytest.mark.asyncio
async def test_patch_venue_toggles_enabled(app_ctx):
    client, _storage, store = app_ctx
    await store.upsert_cex_venue(CexVenue(name="okx", display_name="OKX"))
    r = await client.patch("/api/cex/venues/okx", json={"enabled": False})
    assert r.status_code == 200
    assert (await store.list_cex_venues())[0].enabled is False


@pytest.mark.asyncio
async def test_patch_unknown_venue_returns_404(app_ctx):
    client, *_ = app_ctx
    r = await client.patch("/api/cex/venues/nonesuch", json={"enabled": False})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_latest_rates_shape(app_ctx):
    client, storage, store = app_ctx
    await store.upsert_cex_venue(CexVenue(name="okx", display_name="OKX"))
    now = datetime.now(timezone.utc)
    await storage.insert_cex_rates([
        CexEarnRate(venue="okx", asset="USDT", apy_min=0.04, apy_max=0.05,
                    tier_note="0-500: 5%; 500+: 4%",
                    raw_json='{"secret":"never surface"}',
                    updated_at=now)
    ])
    r = await client.get("/api/cex/rates/latest")
    assert r.status_code == 200
    row = r.json()[0]
    assert row["venue"] == "okx" and row["venue_display"] == "OKX"
    assert row["apy_min"] == 0.04 and row["apy_max"] == 0.05
    assert "raw_json" not in row  # never surfaced by API


@pytest.mark.asyncio
async def test_history_endpoint_filters(app_ctx):
    client, storage, _ = app_ctx
    now = datetime.now(timezone.utc)
    await storage.insert_cex_rates([
        CexEarnRate(venue="okx", asset="USDT", apy_min=0.03, apy_max=0.03,
                    updated_at=now)])
    r = await client.get("/api/cex/rates/history?venue=okx&asset=USDT")
    assert r.status_code == 200 and len(r.json()) == 1


@pytest.mark.asyncio
async def test_refresh_endpoint_persists_rates(app_ctx, monkeypatch):
    """POST /api/cex/refresh runs enabled collectors and writes their rates."""
    client, storage, store = app_ctx
    await store.upsert_cex_venue(CexVenue(name="okx", display_name="OKX",
                                          enabled=True))
    await store.upsert_cex_venue(CexVenue(name="bybit", display_name="Bybit",
                                          enabled=False))  # disabled → skipped

    now = datetime.now(timezone.utc)

    class _FakeSnap:
        def __init__(self, venue, rates, errors=()):
            self.venue = venue
            self.rates = rates
            self.errors = list(errors)

    class _FakeCollector:
        def __init__(self, venue, apy):
            self._venue = venue
            self._apy = apy

        async def collect(self):
            return _FakeSnap(self._venue, [
                CexEarnRate(venue=self._venue, asset="USDT",
                            apy_min=self._apy, apy_max=self._apy,
                            updated_at=now)
            ])

    def _fake_build(v):
        # Only okx should reach here — bybit is disabled and filtered out earlier.
        assert v.name == "okx"
        return _FakeCollector(v.name, 0.055)

    monkeypatch.setattr(
        "stake_watch.api.routes.cex.build_cex_collector", _fake_build
    )

    r = await client.post("/api/cex/refresh")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["venues_refreshed"] == 1
    assert body["rates_written"] == 1

    latest = await client.get("/api/cex/rates/latest")
    rows = latest.json()
    assert len(rows) == 1
    assert rows[0]["venue"] == "okx" and rows[0]["apy_max"] == 0.055


@pytest.mark.asyncio
async def test_refresh_endpoint_with_no_enabled_venues(app_ctx):
    """No enabled venues → success, zero counts, no error."""
    client, *_ = app_ctx
    r = await client.post("/api/cex/refresh")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["venues_refreshed"] == 0
    assert body["rates_written"] == 0