from __future__ import annotations
from decimal import Decimal
from stake_watch.collectors.morpho.models import VaultState

ZERO_ADDRESS = "0x" + "0" * 40

async def read_vault_state(vault_contract, vault_address: str, decimals: int = 6) -> VaultState:
    scale = Decimal(10 ** decimals)
    total_assets = Decimal(await vault_contract.functions.totalAssets().call()) / scale
    total_supply = Decimal(await vault_contract.functions.totalSupply().call()) / scale
    share_price_raw = await vault_contract.functions.convertToAssets(10 ** decimals).call()
    share_price = float(Decimal(share_price_raw) / scale)
    owner = await vault_contract.functions.owner().call()
    curator = await vault_contract.functions.curator().call()
    guardian = await vault_contract.functions.guardian().call()
    fee_raw = await vault_contract.functions.fee().call()
    fee = float(Decimal(fee_raw) / Decimal(10**18)) if fee_raw > 0 else 0.0
    timelock = await vault_contract.functions.timelock().call()
    sq_len = await vault_contract.functions.supplyQueueLength().call()
    wq_len = await vault_contract.functions.withdrawQueueLength().call()
    return VaultState(vault_address=vault_address, vault_version="v1.1",
        total_assets=total_assets, total_supply=total_supply, share_price=share_price,
        owner=owner, curator=curator,
        guardian=guardian if guardian != ZERO_ADDRESS else None,
        fee=fee, timelock=timelock,
        withdraw_queue_length=wq_len, supply_queue_length=sq_len)
