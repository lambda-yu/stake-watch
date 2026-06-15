from __future__ import annotations
from decimal import Decimal
from stake_watch.collectors.morpho.models import MorphoMarketAllocation

async def read_market_allocations(
    vault_contract, morpho_contract, vault_address: str,
    decimals: int = 6, total_vault_assets: Decimal = Decimal("0"),
) -> list[MorphoMarketAllocation]:
    scale = Decimal(10 ** decimals)
    wq_len = await vault_contract.functions.withdrawQueueLength().call()
    allocations = []
    for i in range(wq_len):
        mid_bytes = await vault_contract.functions.withdrawQueue(i).call()
        mid = "0x" + mid_bytes.hex() if isinstance(mid_bytes, bytes) else mid_bytes
        params = await morpho_contract.functions.idToMarketParams(mid_bytes).call()
        loan_token, collateral_token, oracle, irm, lltv_raw = params
        mdata = await morpho_contract.functions.market(mid_bytes).call()
        tsa = Decimal(mdata[0]) / scale
        tba = Decimal(mdata[2]) / scale
        liquidity = tsa - tba
        util = float(tba / tsa) if tsa > 0 else 0.0
        pos = await morpho_contract.functions.position(mid_bytes, vault_address).call()
        vault_shares = Decimal(pos[0])
        total_shares = Decimal(mdata[1])
        vault_assets = (vault_shares * Decimal(mdata[0]) / total_shares / scale) if total_shares > 0 else Decimal("0")
        alloc_pct = float(vault_assets / total_vault_assets * 100) if total_vault_assets > 0 else 0.0
        cap = Decimal(mdata[0]) / scale  # use config cap
        cfg = await vault_contract.functions.config(mid_bytes).call()
        cap = Decimal(cfg[0]) / scale
        allocations.append(MorphoMarketAllocation(
            vault_address=vault_address, market_id=mid,
            loan_token=loan_token, collateral_token=collateral_token,
            oracle=oracle, irm=irm, lltv=float(Decimal(lltv_raw) / Decimal(10**18)),
            supply_assets=vault_assets, borrow_assets=tba,
            liquidity=liquidity, utilization=util,
            allocation_percent=alloc_pct, supply_cap=cap))
    return allocations
