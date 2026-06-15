from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest
from stake_watch.collectors.morpho.oracle import read_oracle_price

@pytest.mark.asyncio
async def test_read_oracle_price():
    m = MagicMock()
    m.functions.price.return_value.call = AsyncMock(return_value=2500 * 10**36)
    r = await read_oracle_price(m, "0xOracle", "0xmarket", "WETH", "USDC")
    assert r.price == Decimal("2500")

@pytest.mark.asyncio
async def test_oracle_reverts():
    m = MagicMock()
    m.functions.price.return_value.call = AsyncMock(side_effect=Exception("revert"))
    with pytest.raises(Exception):
        await read_oracle_price(m, "0xOracle", "0xmarket", "WETH", "USDC")
