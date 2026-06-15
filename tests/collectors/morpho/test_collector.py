from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from stake_watch.collectors.morpho.collector import MorphoCollector
from stake_watch.models.common import Chain

@pytest.mark.asyncio
async def test_morpho_collect_protocol_stats():
    collector = MorphoCollector(
        chain=Chain.BASE, protocol="morpho_steakhouse_usdc",
        vault_address="0xBEEF", morpho_address="0xMorpho", rpc_url="https://fake")

    mock_vault = MagicMock()
    mock_morpho = MagicMock()

    # Vault state mocks
    mock_vault.functions.totalAssets.return_value.call = AsyncMock(return_value=5_000_000_000_000)
    mock_vault.functions.totalSupply.return_value.call = AsyncMock(return_value=4_900_000_000_000)
    mock_vault.functions.convertToAssets.return_value.call = AsyncMock(return_value=1_020_408)
    mock_vault.functions.owner.return_value.call = AsyncMock(return_value="0xOwner")
    mock_vault.functions.curator.return_value.call = AsyncMock(return_value="0xCurator")
    mock_vault.functions.guardian.return_value.call = AsyncMock(return_value="0x" + "0" * 40)
    mock_vault.functions.fee.return_value.call = AsyncMock(return_value=0)
    mock_vault.functions.timelock.return_value.call = AsyncMock(return_value=86400)
    mock_vault.functions.supplyQueueLength.return_value.call = AsyncMock(return_value=1)
    mock_vault.functions.withdrawQueueLength.return_value.call = AsyncMock(return_value=1)
    mock_vault.functions.withdrawQueue.return_value.call = AsyncMock(return_value=b'\x01' * 32)
    mock_vault.functions.config.return_value.call = AsyncMock(return_value=(2_000_000_000_000, True, 0))

    # Morpho state mocks
    mock_morpho.functions.idToMarketParams.return_value.call = AsyncMock(
        return_value=("0xUSDC", "0xWETH", "0xOracle", "0xIRM", 860000000000000000))
    mock_morpho.functions.market.return_value.call = AsyncMock(
        return_value=(1_000_000_000_000, 900_000_000_000, 800_000_000_000, 700_000_000_000, 0, 0))
    mock_morpho.functions.position.return_value.call = AsyncMock(
        return_value=(500_000_000_000, 0, 0))

    with patch.object(collector, '_get_contracts', return_value=(mock_vault, mock_morpho)):
        stats = await collector.collect_protocol_stats()

    assert stats.protocol == "morpho_steakhouse_usdc"
    assert stats.chain == Chain.BASE
    assert stats.tvl_usd > 0
    assert len(stats.pools) == 1
    assert stats.pools[0].utilization == 0.8

@pytest.mark.asyncio
async def test_morpho_collect_positions_empty():
    collector = MorphoCollector(
        chain=Chain.BASE, protocol="test", vault_address="0xV",
        morpho_address="0xM", rpc_url="https://fake")
    positions = await collector.collect_positions("0xWallet")
    assert positions == []
