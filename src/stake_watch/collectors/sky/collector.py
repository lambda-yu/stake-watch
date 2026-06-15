from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from web3 import AsyncWeb3, AsyncHTTPProvider
from stake_watch.collectors.base import BaseCollector
from stake_watch.collectors.sky.abi import SUSDS_ABI
from stake_watch.models.common import Chain, PositionType
from stake_watch.models.position import Position
from stake_watch.models.protocol import ProtocolStats

class SkySusdsCollector(BaseCollector):
    def __init__(self, chain: Chain, protocol: str, susds_address: str, rpc_url: str):
        super().__init__(chain=chain, protocol=protocol)
        self.susds_address = susds_address
        self.rpc_url = rpc_url

    def _get_contract(self):
        w3 = AsyncWeb3(AsyncHTTPProvider(self.rpc_url))
        return w3.eth.contract(address=w3.to_checksum_address(self.susds_address), abi=SUSDS_ABI)

    async def collect_positions(self, wallet: str) -> list[Position]:
        contract = self._get_contract()
        shares = await contract.functions.balanceOf(wallet).call()
        if shares == 0:
            return []
        assets = Decimal(await contract.functions.convertToAssets(shares).call()) / Decimal(10**18)
        return [Position(chain=self.chain, protocol=self.protocol, wallet=wallet,
            asset="USDS", position_type=PositionType.VAULT, amount=assets, value_usd=assets,
            apy=0.0, vault_version="susds", updated_at=datetime.now(timezone.utc))]

    async def collect_protocol_stats(self) -> ProtocolStats:
        return ProtocolStats(chain=self.chain, protocol=self.protocol,
            tvl_usd=Decimal("0"), pools=[], updated_at=datetime.now(timezone.utc))
