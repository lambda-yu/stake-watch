from __future__ import annotations
from decimal import Decimal
from pydantic import BaseModel

class MorphoMarketAllocation(BaseModel):
    vault_address: str
    market_id: str
    loan_token: str
    collateral_token: str
    oracle: str
    irm: str
    lltv: float
    supply_assets: Decimal
    borrow_assets: Decimal
    liquidity: Decimal
    utilization: float
    allocation_percent: float
    supply_cap: Decimal | None = None

class MarketState(BaseModel):
    market_id: str
    total_supply_assets: Decimal
    total_borrow_assets: Decimal
    utilization: float
    available_liquidity: Decimal

class VaultState(BaseModel):
    vault_address: str
    vault_version: str
    total_assets: Decimal
    total_supply: Decimal
    share_price: float
    owner: str
    curator: str
    guardian: str | None = None
    fee: float
    timelock: int
    withdraw_queue_length: int
    supply_queue_length: int

class OracleHealth(BaseModel):
    oracle_address: str
    market_id: str
    price: Decimal
    collateral_token: str
    loan_token: str

class WithdrawalSimResult(BaseModel):
    vault_address: str
    max_withdrawable: Decimal
    can_withdraw_10pct: bool
    can_withdraw_50pct: bool
    can_withdraw_100pct: bool
    your_deposit: Decimal
    liquidity_ratio: float

class BorrowerRisk(BaseModel):
    market_id: str
    borrower: str
    collateral_value: Decimal
    debt: Decimal
    ltv: float
    health_factor: float

class BaseNetworkStatus(BaseModel):
    latest_block: int
    block_age_seconds: float
    gas_price_gwei: float
    is_healthy: bool
