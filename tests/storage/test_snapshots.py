"""Tests for periodic TVL / share-price snapshot writers."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage
from stake_watch.storage.snapshots import (
    write_tvl_snapshots_from_settings,
    write_vault_share_price_snapshots,
)


@pytest.fixture
async def storage(tmp_path):
    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    await s.initialize()
    yield s
    await s.close()


@pytest.fixture
async def store(storage):
    return ConfigStore(storage._session_factory)


async def _seed(store, name, *, chain="base", enabled=True, chains_breakdown=None,
                 vault_address=None):
    await store.add_protocol(name=name, chain=chain, collector="defillama",
                              enabled=enabled, vault_address=vault_address)
    if chains_breakdown is not None:
        await store.set_setting(f"protocols.{name}.chains", chains_breakdown)


# ---------- write_tvl_snapshots_from_settings ----------

@pytest.mark.asyncio
async def test_writes_one_row_per_chain_and_asset(store, storage):
    await _seed(store, "p", chains_breakdown=[
        {"chain": "BASE", "chain_full": "base", "by_asset": {
            "USDC": {"tvl_usd": 1_000_000, "apy": 5.0},
            "USDT": {"tvl_usd": 500_000,   "apy": 4.0}}},
        {"chain": "ETH", "chain_full": "ethereum", "by_asset": {
            "USDC": {"tvl_usd": 2_000_000, "apy": 6.0}}},
    ])
    n = await write_tvl_snapshots_from_settings(store, storage)
    assert n == 3
    # Round-trip: get TVL from N days ago (0 days = latest)
    v = await storage.get_tvl_n_days_ago("p", "base", "USDC", 0)
    assert v == 1_000_000


@pytest.mark.asyncio
async def test_skips_zero_tvl(store, storage):
    await _seed(store, "p", chains_breakdown=[
        {"chain": "BASE", "chain_full": "base", "by_asset": {
            "USDC": {"tvl_usd": 0, "apy": 0}}},
    ])
    n = await write_tvl_snapshots_from_settings(store, storage)
    assert n == 0


@pytest.mark.asyncio
async def test_skips_disabled_protocols(store, storage):
    await _seed(store, "off", enabled=False, chains_breakdown=[
        {"chain": "BASE", "chain_full": "base", "by_asset": {
            "USDC": {"tvl_usd": 1_000_000, "apy": 5.0}}},
    ])
    n = await write_tvl_snapshots_from_settings(store, storage)
    assert n == 0


@pytest.mark.asyncio
async def test_name_filter_limits_scope(store, storage):
    await _seed(store, "a", chains_breakdown=[
        {"chain": "BASE", "chain_full": "base", "by_asset": {
            "USDC": {"tvl_usd": 1, "apy": 1}}}])
    await _seed(store, "b", chains_breakdown=[
        {"chain": "BASE", "chain_full": "base", "by_asset": {
            "USDC": {"tvl_usd": 1, "apy": 1}}}])
    n = await write_tvl_snapshots_from_settings(store, storage, names=["a"])
    assert n == 1


@pytest.mark.asyncio
async def test_no_chains_breakdown_writes_zero(store, storage):
    await _seed(store, "p")  # no chains setting
    n = await write_tvl_snapshots_from_settings(store, storage)
    assert n == 0


# ---------- write_vault_share_price_snapshots ----------

@pytest.mark.asyncio
async def test_share_price_writes_one_per_morpho_protocol(store, storage):
    await _seed(store, "morpho_steakhouse_usdc",
                 vault_address="0xBEEFE94c8aD530842bfE7d8B397938fFc1cb83b2")
    await _seed(store, "aave_v3_base")  # no vault → skipped
    with patch("stake_watch.collectors.morpho.morpho_api.fetch_vault_data",
                AsyncMock(return_value={"asset": "USDC", "tvl_usd": 1, "apy": 5,
                                          "share_price_usd": 1.0001})):
        n = await write_vault_share_price_snapshots(store, storage)
    assert n == 1
    latest = await storage.get_latest_vault_share_price(
        "0xBEEFE94c8aD530842bfE7d8B397938fFc1cb83b2")
    assert latest == pytest.approx(1.0001)


@pytest.mark.asyncio
async def test_share_price_skips_solana_protocols(store, storage):
    await _seed(store, "kamino_usdc", chain="solana",
                 vault_address="solanaaddr")
    with patch("stake_watch.collectors.morpho.morpho_api.fetch_vault_data",
                AsyncMock(return_value={"share_price_usd": 1.0})):
        n = await write_vault_share_price_snapshots(store, storage)
    assert n == 0


@pytest.mark.asyncio
async def test_share_price_handles_fetch_failure(store, storage):
    await _seed(store, "morpho_x", vault_address="0xabc")
    with patch("stake_watch.collectors.morpho.morpho_api.fetch_vault_data",
                AsyncMock(side_effect=Exception("api down"))):
        n = await write_vault_share_price_snapshots(store, storage)
    assert n == 0
