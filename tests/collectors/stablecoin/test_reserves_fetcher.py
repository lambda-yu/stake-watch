from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest
from stake_watch.collectors.stablecoin.reserves_fetcher import (
    fetch_tether_reserves, fetch_circle_supply,
)

MOCK_TETHER = {
    "iso": "usdt",
    "symbol": "$",
    "total_assets": "192016079438.59",
    "total_liabilities": "186549137803.95",
    "shareholders_equity": "5466941634.63",
    "tokens": [
        {"name": "Ethereum", "total_authorized": "97070655229.72", "reserve_balance": "3593575936.80"},
        {"name": "Tron", "total_authorized": "89341574028.13", "reserve_balance": "1551691772.57"},
    ],
}

MOCK_CIRCLE = {
    "name": "USD Coin",
    "symbol": "USDC",
    "totalAmount": "74857920757.90",
    "chains": [
        {"chain": "ETH", "amount": "51746182930.21", "updateDate": "2026-06-15T12:38:33Z"},
        {"chain": "SOL", "amount": "7161389754.22", "updateDate": "2026-06-15T12:38:33Z"},
        {"chain": "BASE", "amount": "4231791011.47", "updateDate": "2026-06-15T12:38:34Z"},
    ],
}


@pytest.mark.asyncio
async def test_fetch_tether():
    async def fake_get(*a, **k):
        r = MagicMock()
        r.json = MagicMock(return_value=[MOCK_TETHER])
        r.raise_for_status = MagicMock()
        return r

    with patch("httpx.AsyncClient.get", new=fake_get):
        result = await fetch_tether_reserves()

    assert result is not None
    assert result["token"] == "USDT"
    assert result["total_assets"] == Decimal("192016079438.59")
    assert result["coverage_ratio"] > 1.0
    assert "Ethereum" in result["chains"]
    assert "Tron" in result["chains"]


@pytest.mark.asyncio
async def test_fetch_circle():
    async def fake_get(*a, **k):
        r = MagicMock()
        r.json = MagicMock(return_value=[MOCK_CIRCLE])
        r.raise_for_status = MagicMock()
        return r

    with patch("httpx.AsyncClient.get", new=fake_get):
        result = await fetch_circle_supply()

    assert result is not None
    assert result["token"] == "USDC"
    assert result["total_supply"] == Decimal("74857920757.90")
    assert "ETH" in result["chains"]
    assert "BASE" in result["chains"]


@pytest.mark.asyncio
async def test_fetch_tether_failure():
    async def fail(*a, **k):
        raise Exception("network error")

    with patch("httpx.AsyncClient.get", new=fail):
        result = await fetch_tether_reserves()
    assert result is None


@pytest.mark.asyncio
async def test_fetch_circle_failure():
    async def fail(*a, **k):
        raise Exception("network error")

    with patch("httpx.AsyncClient.get", new=fail):
        result = await fetch_circle_supply()
    assert result is None
