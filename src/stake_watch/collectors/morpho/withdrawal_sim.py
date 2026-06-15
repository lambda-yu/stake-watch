from __future__ import annotations
from decimal import Decimal
from stake_watch.collectors.morpho.models import WithdrawalSimResult

async def simulate_withdrawal(vault_contract, vault_address: str, user_address: str, decimals: int = 6) -> WithdrawalSimResult:
    scale = Decimal(10 ** decimals)
    shares = await vault_contract.functions.balanceOf(user_address).call()
    deposit = Decimal(await vault_contract.functions.convertToAssets(shares).call()) / scale
    max_w = Decimal(await vault_contract.functions.maxWithdraw(user_address).call()) / scale
    ratio = float(max_w / deposit) if deposit > 0 else 0.0
    return WithdrawalSimResult(vault_address=vault_address, max_withdrawable=max_w,
        can_withdraw_10pct=max_w >= deposit * Decimal("0.1"),
        can_withdraw_50pct=max_w >= deposit * Decimal("0.5"),
        can_withdraw_100pct=max_w >= deposit,
        your_deposit=deposit, liquidity_ratio=ratio)
