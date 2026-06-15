from datetime import datetime, timezone
import pytest
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage

@pytest.fixture
async def config_store(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    storage = Storage(db_url)
    await storage.initialize()
    store = ConfigStore(storage._session_factory)
    yield store
    await storage.close()

@pytest.mark.asyncio
async def test_wallet_crud(config_store):
    wallet = await config_store.add_wallet("base", "0xTest", "My Wallet")
    assert wallet.chain == "base"
    assert wallet.address == "0xTest"
    assert wallet.id is not None
    wallets = await config_store.list_wallets()
    assert len(wallets) == 1
    await config_store.delete_wallet(wallet.id)
    wallets = await config_store.list_wallets()
    assert len(wallets) == 0

@pytest.mark.asyncio
async def test_rpc_crud(config_store):
    await config_store.upsert_rpc("base", "https://mainnet.base.org", [])
    rpc = await config_store.get_rpc("base")
    assert rpc is not None
    assert rpc.primary_url == "https://mainnet.base.org"
    await config_store.upsert_rpc("base", "https://new-rpc.base.org", ["https://fallback.base.org"])
    rpc = await config_store.get_rpc("base")
    assert rpc.primary_url == "https://new-rpc.base.org"

@pytest.mark.asyncio
async def test_protocol_crud(config_store):
    proto = await config_store.add_protocol(
        name="aave_v3_base", chain="base", collector="defillama",
        defillama_slug="aave-v3", safety_score=8.8, enabled=True)
    assert proto.name == "aave_v3_base"
    await config_store.toggle_protocol(proto.id)
    updated = await config_store.get_protocol(proto.id)
    assert updated.enabled is False
    all_protos = await config_store.list_protocols()
    assert len(all_protos) == 1

@pytest.mark.asyncio
async def test_app_settings_crud(config_store):
    await config_store.set_setting("intervals.positions", 300)
    val = await config_store.get_setting("intervals.positions")
    assert val == 300
    await config_store.set_setting("intervals.positions", 60)
    val = await config_store.get_setting("intervals.positions")
    assert val == 60

@pytest.mark.asyncio
async def test_load_full_settings(config_store):
    await config_store.set_setting("intervals.positions", 300)
    await config_store.set_setting("intervals.protocol_stats", 900)
    await config_store.set_setting("risk.liquidation_warning", 1.3)
    settings = await config_store.load_app_settings()
    assert settings.intervals.positions == 300
    assert settings.risk.liquidation_warning == 1.3
