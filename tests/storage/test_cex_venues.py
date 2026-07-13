import json
import pytest
from stake_watch.storage.db import Storage
from stake_watch.storage.config_store import ConfigStore
from stake_watch.models.cex import CexVenue


@pytest.fixture
async def store():
    s = Storage("sqlite+aiosqlite:///:memory:")
    await s.initialize()
    yield ConfigStore(s._session_factory)
    await s.close()


@pytest.mark.asyncio
async def test_upsert_then_list(store):
    await store.upsert_cex_venue(CexVenue(name="okx", display_name="OKX"))
    rows = await store.list_cex_venues()
    assert len(rows) == 1 and rows[0].name == "okx"
    assert json.loads(rows[0].assets_json) == ["USDT", "USDC"]


@pytest.mark.asyncio
async def test_upsert_updates_and_bumps_updated_at(store):
    await store.upsert_cex_venue(CexVenue(name="okx", display_name="OKX"))
    first = (await store.list_cex_venues())[0].updated_at
    await store.upsert_cex_venue(CexVenue(name="okx", display_name="OKX Global"))
    row = (await store.list_cex_venues())[0]
    assert row.display_name == "OKX Global"
    assert row.updated_at >= first


@pytest.mark.asyncio
async def test_patch_toggles_enabled_and_assets(store):
    await store.upsert_cex_venue(CexVenue(name="okx", display_name="OKX"))
    await store.patch_cex_venue("okx", enabled=False, assets=["USDT"])
    row = (await store.list_cex_venues())[0]
    assert row.enabled is False
    assert json.loads(row.assets_json) == ["USDT"]


@pytest.mark.asyncio
async def test_patch_unknown_returns_none(store):
    result = await store.patch_cex_venue("nonesuch", enabled=False)
    assert result is None


@pytest.mark.asyncio
async def test_list_enabled_filters(store):
    await store.upsert_cex_venue(CexVenue(name="okx", display_name="OKX"))
    await store.upsert_cex_venue(CexVenue(name="binance", display_name="Binance",
                                          enabled=False))
    enabled = await store.list_enabled_cex_venues()
    assert [v.name for v in enabled] == ["okx"]


@pytest.mark.asyncio
async def test_seed_is_idempotent_for_cex(store, tmp_path):
    seed = tmp_path / "seed.yaml"
    seed.write_text(
        "cex_venues:\n"
        "  - {name: okx, display_name: OKX, enabled: true, assets: [USDT, USDC]}\n"
    )
    await store.import_seed_if_empty(str(seed))
    await store.import_seed_if_empty(str(seed))  # second run must be a no-op
    assert len(await store.list_cex_venues()) == 1


@pytest.mark.asyncio
async def test_seed_cex_when_protocols_already_exist(store, tmp_path):
    """Upgrade path: DB has protocols but no CEX venues — CEX must still seed."""
    await store.add_protocol(name="fake", chain="ethereum", collector="defillama")
    seed = tmp_path / "seed.yaml"
    seed.write_text(
        "cex_venues:\n"
        "  - {name: okx, display_name: OKX, enabled: true, assets: [USDT, USDC]}\n"
    )
    await store.import_seed_if_empty(str(seed))
    assert len(await store.list_cex_venues()) == 1