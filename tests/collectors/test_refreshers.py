"""Tests for the per-protocol-family refresh dispatcher."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from stake_watch.collectors.refreshers import (
    REFRESHERS,
    pick_refresher,
    refresh_aave,
    refresh_compound,
    refresh_jupiter,
    refresh_kamino,
    refresh_morpho,
    refresh_sky,
)
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage


class _Proto:
    def __init__(self, **kw):
        self.name = kw.get("name", "x")
        self.chain = kw.get("chain", "base")
        self.collector = kw.get("collector", "defillama")
        self.vault_address = kw.get("vault_address")
        self.enabled = kw.get("enabled", True)


# ---------- pick_refresher dispatch table ----------

def test_morpho_picked_when_vault_address_and_evm_chain():
    p = _Proto(name="morpho_steakhouse_usdc", chain="base",
                vault_address="0xabc")
    source, fn = pick_refresher(p)
    assert source == "Morpho API"
    assert fn is refresh_morpho


def test_morpho_not_picked_without_vault_address():
    p = _Proto(name="morpho_steakhouse_usdc", chain="base")
    assert pick_refresher(p) is None


def test_morpho_not_picked_on_solana():
    p = _Proto(name="morpho_x", chain="solana", vault_address="0xabc")
    assert pick_refresher(p) is None


def test_kamino_picked_by_name_prefix():
    p = _Proto(name="kamino_usdc", chain="solana")
    source, fn = pick_refresher(p)
    assert source == "Kamino API"
    assert fn is refresh_kamino


def test_kamino_picked_by_collector_field():
    p = _Proto(name="weird_name", chain="solana", collector="kamino")
    assert pick_refresher(p)[1] is refresh_kamino


def test_jupiter_picked_by_name_prefix():
    p = _Proto(name="jupiter_lend", chain="solana")
    assert pick_refresher(p)[1] is refresh_jupiter


def test_aave_picked_by_name_prefix():
    p = _Proto(name="aave_v3_base", chain="base")
    assert pick_refresher(p)[1] is refresh_aave


def test_compound_picked_by_name_prefix():
    p = _Proto(name="compound_v3_usdc", chain="base")
    assert pick_refresher(p)[1] is refresh_compound


def test_sky_picked_by_exact_name():
    p = _Proto(name="sky_susds", chain="ethereum")
    assert pick_refresher(p)[1] is refresh_sky


def test_unknown_protocol_returns_none():
    p = _Proto(name="fluid_usdc", chain="ethereum")  # falls through to DefiLlama
    assert pick_refresher(p) is None


def test_morpho_takes_precedence_over_name_prefix():
    # Morpho is first in REFRESHERS list — even if name happens to start with
    # "aave_" (it wouldn't in practice), vault_address + EVM chain wins.
    p = _Proto(name="aave_v3_base", chain="base", vault_address="0xabc")
    source, _ = pick_refresher(p)
    assert source == "Morpho API"


def test_registry_order_is_specificity_first():
    """Predicates must be checked in this order for correctness."""
    sources = [s for s, _, _ in REFRESHERS]
    assert sources[0] == "Morpho API"  # vault_address gate is most specific


# ---------- end-to-end with a real sqlite store ----------

@pytest.fixture
async def storage(tmp_path):
    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    await s.initialize()
    yield s
    await s.close()


@pytest.fixture
async def store(storage):
    return ConfigStore(storage._session_factory)


@pytest.mark.asyncio
async def test_refresh_kamino_persists_pools_and_chains(store, storage):
    p = await store.add_protocol(name="kamino_usdc", chain="solana",
                                   collector="kamino")
    reserves = [
        {"asset": "USDC", "apy": 6.5, "tvl_usd": 10_000_000,
         "utilization": 0.7, "withdrawable_ratio": 0.3,
         "available_liquidity_usd": 3_000_000},
        {"asset": "USDT", "apy": 4.0, "tvl_usd": 2_000_000,
         "utilization": 0.4, "withdrawable_ratio": 0.6,
         "available_liquidity_usd": 1_200_000},
    ]
    with patch("stake_watch.collectors.kamino.kamino_api.fetch_kamino_stable_reserves",
                AsyncMock(return_value=reserves)):
        entry = await refresh_kamino(p, store, storage)

    assert entry["name"] == "kamino_usdc"
    assert entry["source"] == "Kamino API"
    assert entry["tvl_usd"] == 12_000_000
    assert entry["pools"] == 2
    chains = await store.get_setting("protocols.kamino_usdc.chains")
    assert chains[0]["chain"] == "SOL"
    assert set(chains[0]["by_asset"]) == {"USDC", "USDT"}


@pytest.mark.asyncio
async def test_refresh_kamino_returns_none_when_empty(store, storage):
    p = await store.add_protocol(name="kamino_usdc", chain="solana",
                                   collector="kamino")
    with patch("stake_watch.collectors.kamino.kamino_api.fetch_kamino_stable_reserves",
                AsyncMock(return_value=[])):
        entry = await refresh_kamino(p, store, storage)
    assert entry is None


@pytest.mark.asyncio
async def test_refresh_aave_picks_primary_chain_entry(store, storage):
    p = await store.add_protocol(name="aave_v3_base", chain="base",
                                   collector="defillama")
    chains_data = [
        {"chain": "ETH", "chain_full": "Ethereum", "tvl_usd": 1, "apy": 4.0,
         "pools": 1, "by_asset": {"USDC": {"apy": 4.0, "tvl_usd": 1_000_000}}},
        {"chain": "BASE", "chain_full": "Base", "tvl_usd": 1, "apy": 5.0,
         "pools": 1, "by_asset": {"USDC": {"apy": 5.0, "tvl_usd": 50_000_000}}},
    ]
    with patch("stake_watch.collectors.aave.aave_api.fetch_aave_v3_stable_data",
                AsyncMock(return_value=chains_data)):
        entry = await refresh_aave(p, store, storage)

    # Primary chain for aave_v3_base is Base → tvl from BASE entry
    assert entry["tvl_usd"] == 50_000_000
    assert entry["apy"] == 5.0
    assert entry["chains"] == 2  # both ETH + BASE persisted in chains setting
    assert entry["source"] == "Aave V3 API"


@pytest.mark.asyncio
async def test_refresh_sky_raises_when_no_eth_rpc(store, storage):
    p = await store.add_protocol(name="sky_susds", chain="ethereum",
                                   collector="defillama")
    with pytest.raises(RuntimeError, match="no ethereum RPC"):
        await refresh_sky(p, store, storage)


@pytest.mark.asyncio
async def test_refresh_sky_persists_when_rpc_succeeds(store, storage):
    p = await store.add_protocol(name="sky_susds", chain="ethereum",
                                   collector="defillama")
    await store.upsert_rpc("ethereum", "https://eth", [])
    with patch("stake_watch.collectors.sky.sky_api.fetch_sky_susds_data",
                AsyncMock(return_value={"asset": "USDS", "apy": 4.95,
                                          "tvl_usd": 9_000_000_000})):
        entry = await refresh_sky(p, store, storage)
    assert entry["tvl_usd"] == 9_000_000_000
    assert entry["source"] == "Sky on-chain (SSR)"


@pytest.mark.asyncio
async def test_refresh_morpho_returns_none_when_vault_unknown(store, storage):
    p = await store.add_protocol(name="morpho_steakhouse_usdc", chain="base",
                                   collector="morpho",
                                   vault_address="0xbeef")
    with patch("stake_watch.collectors.morpho.morpho_api.fetch_vault_data",
                AsyncMock(return_value=None)):
        entry = await refresh_morpho(p, store, storage)
    assert entry is None
