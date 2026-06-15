from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest
from stake_watch.collectors.morpho.withdrawal_sim import simulate_withdrawal

@pytest.mark.asyncio
async def test_withdrawal_full():
    m = MagicMock()
    m.functions.balanceOf.return_value.call = AsyncMock(return_value=1000_000_000)
    m.functions.convertToAssets.return_value.call = AsyncMock(return_value=1020_000_000)
    m.functions.maxWithdraw.return_value.call = AsyncMock(return_value=1020_000_000)
    r = await simulate_withdrawal(m, "0xV", "0xU", decimals=6)
    assert r.your_deposit == Decimal("1020")
    assert r.can_withdraw_100pct is True
    assert r.liquidity_ratio >= 1.0

@pytest.mark.asyncio
async def test_withdrawal_partial():
    m = MagicMock()
    m.functions.balanceOf.return_value.call = AsyncMock(return_value=1000_000_000)
    m.functions.convertToAssets.return_value.call = AsyncMock(return_value=1000_000_000)
    m.functions.maxWithdraw.return_value.call = AsyncMock(return_value=600_000_000)
    r = await simulate_withdrawal(m, "0xV", "0xU", decimals=6)
    assert r.can_withdraw_50pct is True
    assert r.can_withdraw_100pct is False
    assert r.liquidity_ratio < 1.0
