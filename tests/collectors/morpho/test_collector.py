from decimal import Decimal
from unittest.mock import AsyncMock, patch
import pytest
from stake_watch.collectors.morpho.collector import MorphoCollector
from stake_watch.models.common import Chain

@pytest.mark.asyncio
async def test_morpho_collect_protocol_stats_uses_graphql_api():
    """TVL/APY come from Morpho's GraphQL API (1 request), not per-market
    on-chain reads — the on-chain path made ~40 sequential eth_calls per
    vault and reliably triggered 429s on the free Base RPC."""
    collector = MorphoCollector(
        chain=Chain.BASE, protocol="morpho_steakhouse_usdc",
        vault_address="0xBEEF", morpho_address="0xMorpho", rpc_url="https://fake")

    fake_vault_data = {
        "name": "Steakhouse Prime USDC", "asset": "USDC", "symbol": "steakUSDC",
        "tvl_usd": 21523923.31, "apy": 4.12, "net_apy": 3.91,
        "share_price_usd": 1.0537, "withdrawable_usd": 21523923.31,
        "available_liquidity_usd": 21523923.31, "withdrawable_ratio": 1.0,
        "utilization": 0.0,
    }

    with patch("stake_watch.collectors.morpho.collector.fetch_vault_data",
               new=AsyncMock(return_value=fake_vault_data)) as mock_fetch:
        stats = await collector.collect_protocol_stats()

    mock_fetch.assert_awaited_once_with("0xBEEF", "base")
    assert stats.protocol == "morpho_steakhouse_usdc"
    assert stats.chain == Chain.BASE
    assert stats.tvl_usd == Decimal(str(fake_vault_data["tvl_usd"]))
    assert len(stats.pools) == 1
    assert stats.pools[0].asset == "USDC"
    assert stats.pools[0].supply_apy == 4.12
    assert stats.pools[0].utilization == 0.0


@pytest.mark.asyncio
async def test_morpho_collect_protocol_stats_raises_on_empty_response():
    """fetch_vault_data returning None (vault not found / API error) should
    surface as an exception so BaseCollector records it as a failure rather
    than silently persisting zeroed-out stats."""
    collector = MorphoCollector(
        chain=Chain.BASE, protocol="morpho_steakhouse_usdc",
        vault_address="0xBEEF", morpho_address="0xMorpho", rpc_url="https://fake")

    with patch("stake_watch.collectors.morpho.collector.fetch_vault_data",
               new=AsyncMock(return_value=None)):
        with pytest.raises(RuntimeError):
            await collector.collect_protocol_stats()

@pytest.mark.asyncio
async def test_morpho_collect_positions_empty():
    collector = MorphoCollector(
        chain=Chain.BASE, protocol="test", vault_address="0xV",
        morpho_address="0xM", rpc_url="https://fake")
    positions = await collector.collect_positions("0xWallet")
    assert positions == []
