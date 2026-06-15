from __future__ import annotations
from decimal import Decimal
from stake_watch.collectors.morpho.models import OracleHealth

PRICE_SCALE = Decimal(10**36)

async def read_oracle_price(oracle_contract, oracle_address: str, market_id: str,
    collateral_token: str, loan_token: str) -> OracleHealth:
    raw = await oracle_contract.functions.price().call()
    price = Decimal(raw) / PRICE_SCALE
    return OracleHealth(oracle_address=oracle_address, market_id=market_id,
        price=price, collateral_token=collateral_token, loan_token=loan_token)
