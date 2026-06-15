from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from web3 import AsyncWeb3, AsyncHTTPProvider
from stake_watch.collectors.base import BaseCollector
from stake_watch.collectors.aave.abi import AAVE_V3_POOL_ABI
from stake_watch.models.common import Chain, PositionType
from stake_watch.models.position import Position
from stake_watch.models.protocol import ProtocolStats

class AaveV3Collector(BaseCollector):
    def __init__(self, chain: Chain, protocol: str, pool_address: str, rpc_url: str):
        super().__init__(chain=chain, protocol=protocol)
        self.pool_address = pool_address
        self.rpc_url = rpc_url

    def _get_pool_contract(self):
        w3 = AsyncWeb3(AsyncHTTPProvider(self.rpc_url))
        return w3.eth.contract(address=w3.to_checksum_address(self.pool_address), abi=AAVE_V3_POOL_ABI)

    async def collect_positions(self, wallet: str) -> list[Position]:
        pool = self._get_pool_contract()
        data = await pool.functions.getUserAccountData(wallet).call()
        total_collateral = Decimal(data[0]) / Decimal(10**8)
        health_factor_raw = data[5]
        hf = float(Decimal(health_factor_raw) / Decimal(10**18)) if health_factor_raw > 0 else None
        ltv = float(Decimal(data[4]) / Decimal(10**4)) if data[4] > 0 else None
        if total_collateral == 0:
            return []
        return [Position(chain=self.chain, protocol=self.protocol, wallet=wallet,
            asset="USDC", position_type=PositionType.SUPPLY, amount=total_collateral,
            value_usd=total_collateral, apy=0.0, ltv=ltv, health_factor=hf,
            updated_at=datetime.now(timezone.utc))]

    async def collect_protocol_stats(self) -> ProtocolStats:
        return ProtocolStats(chain=self.chain, protocol=self.protocol,
            tvl_usd=Decimal("0"), pools=[], updated_at=datetime.now(timezone.utc))
