from decimal import Decimal
from unittest.mock import MagicMock, patch, AsyncMock
import pytest
from stake_watch.collectors.stablecoin.dex_liquidity import (
    DexLiquidityCollector, _estimate_slippage, DexPoolSnapshot,
)

MOCK_POOL_RESP = {
    "data": {
        "attributes": {
            "name": "USDC / USDT 0.01%",
            "reserve_in_usd": "20000000",
            "base_token_price_usd": "0.9998",
            "quote_token_price_usd": "1.0001",
            "volume_usd": {"h1": "500000", "h24": "10000000"},
        }
    }
}


@pytest.mark.asyncio
async def test_collect_pools():
    collector = DexLiquidityCollector()

    async def fake_get(*args, **kwargs):
        r = MagicMock()
        r.json = MagicMock(return_value=MOCK_POOL_RESP)
        r.raise_for_status = MagicMock()
        return r

    with patch("httpx.AsyncClient.get", new=fake_get):
        pools = await collector.collect_pools()

    assert len(pools) >= 1
    p = pools[0]
    assert p.reserve_usd == Decimal("20000000")
    assert p.base_price_usd == 0.9998
    assert p.volume_24h_usd == Decimal("10000000")
    assert p.estimated_slippage_1m > 0


def test_slippage_estimation():
    assert _estimate_slippage(100_000, 20_000_000) == 0.5
    assert _estimate_slippage(1_000_000, 20_000_000) == 5.0
    assert _estimate_slippage(5_000_000, 20_000_000) == 25.0


def test_slippage_zero_tvl():
    assert _estimate_slippage(100_000, 0) == 100.0


@pytest.mark.asyncio
async def test_collect_handles_failure():
    collector = DexLiquidityCollector()

    async def fail_get(*args, **kwargs):
        raise Exception("network error")

    with patch("httpx.AsyncClient.get", new=fail_get):
        pools = await collector.collect_pools()

    assert pools == []
