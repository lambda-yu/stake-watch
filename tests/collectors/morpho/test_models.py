from decimal import Decimal
from stake_watch.collectors.morpho.models import (
    MorphoMarketAllocation, VaultState, MarketState, OracleHealth,
    WithdrawalSimResult, BaseNetworkStatus)

def test_market_allocation():
    m = MorphoMarketAllocation(vault_address="0xBEEF", market_id="0xabc",
        loan_token="USDC", collateral_token="WETH", oracle="0xO", irm="0xI",
        lltv=0.86, supply_assets=Decimal("1000000"), borrow_assets=Decimal("800000"),
        liquidity=Decimal("200000"), utilization=0.8, allocation_percent=50.0,
        supply_cap=Decimal("2000000"))
    assert m.utilization == 0.8

def test_vault_state():
    v = VaultState(vault_address="0xBEEF", vault_version="v1.1",
        total_assets=Decimal("5000000"), total_supply=Decimal("4900000"),
        share_price=1.0204, owner="0xO", curator="0xC", fee=0.1,
        timelock=86400, withdraw_queue_length=3, supply_queue_length=3)
    assert v.share_price > 1.0

def test_withdrawal_sim():
    w = WithdrawalSimResult(vault_address="0xV", max_withdrawable=Decimal("1000"),
        can_withdraw_10pct=True, can_withdraw_50pct=True, can_withdraw_100pct=True,
        your_deposit=Decimal("1000"), liquidity_ratio=1.0)
    assert w.can_withdraw_100pct

def test_base_network():
    b = BaseNetworkStatus(latest_block=1000000, block_age_seconds=5.0,
        gas_price_gwei=0.1, is_healthy=True)
    assert b.is_healthy
