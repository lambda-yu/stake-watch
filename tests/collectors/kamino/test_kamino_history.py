"""Tests for Kamino native /metrics/history fetcher."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stake_watch.collectors.kamino.kamino_history import (
    ASSET_MINTS,
    fetch_reserve_history,
)


def _patch_get(body, raise_exc=None):
    client = MagicMock()
    if raise_exc:
        client.get = AsyncMock(side_effect=raise_exc)
    else:
        resp = MagicMock()
        resp.json = MagicMock(return_value=body)
        resp.raise_for_status = MagicMock()
        client.get = AsyncMock(return_value=resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("httpx.AsyncClient", return_value=ctx)


@pytest.mark.asyncio
async def test_parses_flat_list_response():
    now = datetime.now(timezone.utc)
    body = [
        {"timestamp": now.replace(hour=0).isoformat(),
         "metrics": {"supplyApy": 0.061, "totalSupplyUsd": 12_000_000}},
        {"timestamp": now.replace(hour=6).isoformat(),
         "metrics": {"supplyApy": 0.058, "totalSupplyUsd": 12_500_000}},
    ]
    with _patch_get(body):
        points = await fetch_reserve_history("USDC", days=7)
    assert len(points) == 2
    assert points[0]["apy"] == pytest.approx(6.1)
    assert points[1]["apy"] == pytest.approx(5.8)
    assert points[0]["tvl_usd"] == 12_000_000
    # Sorted ascending
    assert points[0]["t"] < points[1]["t"]


@pytest.mark.asyncio
async def test_parses_wrapped_response_shape():
    """Some versions of the API wrap the list under a `history` or `data` key."""
    now = datetime.now(timezone.utc)
    body = {"history": [
        {"timestamp": now.isoformat(),
         "metrics": {"supplyApy": 0.05, "totalSupplyUsd": 1}},
    ]}
    with _patch_get(body):
        points = await fetch_reserve_history("USDC", days=7)
    assert len(points) == 1
    assert points[0]["apy"] == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_tolerates_flat_metrics_keys():
    """Some responses put metrics fields inline instead of under `metrics`."""
    now = datetime.now(timezone.utc)
    body = [
        {"timestamp": now.isoformat(),
         "supplyApy": 0.045, "totalSupplyUsd": 8_000_000},
    ]
    with _patch_get(body):
        points = await fetch_reserve_history("USDC", days=7)
    assert len(points) == 1
    assert points[0]["apy"] == pytest.approx(4.5)


@pytest.mark.asyncio
async def test_returns_empty_for_unknown_asset():
    points = await fetch_reserve_history("XYZ", days=7)
    assert points == []


@pytest.mark.asyncio
async def test_returns_empty_on_upstream_error():
    with _patch_get(None, raise_exc=Exception("net down")):
        points = await fetch_reserve_history("USDC", days=7)
    assert points == []


@pytest.mark.asyncio
async def test_skips_points_missing_apy():
    now = datetime.now(timezone.utc)
    body = [
        {"timestamp": now.isoformat(),
         "metrics": {"totalSupplyUsd": 1}},   # no apy → skip
        {"timestamp": now.isoformat(),
         "metrics": {"supplyApy": 0.05, "totalSupplyUsd": 1}},
    ]
    with _patch_get(body):
        points = await fetch_reserve_history("USDC", days=7)
    assert len(points) == 1


def test_asset_mints_covers_stables():
    assert ASSET_MINTS["USDC"].startswith("EPjF")  # canonical USDC mint
    assert "USDT" in ASSET_MINTS
