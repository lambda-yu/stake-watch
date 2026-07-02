"""Tests for Sky SSR history via Block Analitica fallback chain."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stake_watch.collectors.sky.sky_history import fetch_ssr_history


def _patch(by_path, error_paths=None):
    """Programmable httpx.AsyncClient.get(): dispatches by path substring."""
    error_paths = error_paths or set()

    async def _get(url, *args, **kwargs):
        for path, body in by_path.items():
            if path in url:
                if path in error_paths:
                    raise RuntimeError("mock error")
                resp = MagicMock()
                resp.json = MagicMock(return_value=body)
                resp.raise_for_status = MagicMock()
                return resp
        resp = MagicMock()
        resp.json = MagicMock(return_value=[])
        resp.raise_for_status = MagicMock()
        return resp

    client = MagicMock()
    client.get = AsyncMock(side_effect=_get)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("httpx.AsyncClient", return_value=ctx)


@pytest.mark.asyncio
async def test_parses_date_and_rate_normalized_to_percent():
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    body = [
        {"date": yesterday, "rate": "0.048", "tvl": "9000000000"},
        {"date": today,     "rate": "0.052", "tvl": "9200000000"},
    ]
    with _patch({"/susds/rates/history/": body}):
        points = await fetch_ssr_history(days=7)
    assert len(points) == 2
    assert points[0]["apy"] == pytest.approx(4.8)
    assert points[1]["apy"] == pytest.approx(5.2)
    assert points[1]["tvl_usd"] == 9_200_000_000


@pytest.mark.asyncio
async def test_falls_through_to_second_candidate_path():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # First candidate empty, second has data
    body = [{"date": today, "rate": 0.055, "tvl": 1}]
    with _patch({"/savings-rate/": body}):
        points = await fetch_ssr_history(days=7)
    assert len(points) == 1
    assert points[0]["apy"] == pytest.approx(5.5)


@pytest.mark.asyncio
async def test_filters_older_than_days_window():
    old = (datetime.now(timezone.utc) - timedelta(days=45)).strftime("%Y-%m-%d")
    recent = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    body = [
        {"date": old,    "rate": 0.03, "tvl": 1},
        {"date": recent, "rate": 0.05, "tvl": 1},
    ]
    with _patch({"/susds/rates/history/": body}):
        points = await fetch_ssr_history(days=7)
    assert len(points) == 1
    assert points[0]["apy"] == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_handles_wrapped_response_shape():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    body = {"results": [{"date": today, "rate": 0.05, "tvl": 1}]}
    with _patch({"/susds/rates/history/": body}):
        points = await fetch_ssr_history(days=7)
    assert len(points) == 1


@pytest.mark.asyncio
async def test_returns_empty_when_all_candidates_fail():
    with _patch({}, error_paths=set()):
        points = await fetch_ssr_history(days=7)
    assert points == []


@pytest.mark.asyncio
async def test_rate_already_in_percent_not_double_scaled():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Some responses return rate already as %, not fraction.
    body = [{"date": today, "rate": 5.5, "tvl": 1}]
    with _patch({"/susds/rates/history/": body}):
        points = await fetch_ssr_history(days=7)
    assert len(points) == 1
    # >= 1.0 → assume already percent
    assert points[0]["apy"] == pytest.approx(5.5)
