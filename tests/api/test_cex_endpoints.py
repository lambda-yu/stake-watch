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