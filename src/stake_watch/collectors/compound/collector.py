from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from web3 import AsyncWeb3, AsyncHTTPProvider
from stake_watch.collectors.base import BaseCollector
from stake_watch.collectors.compound.abi import COMET_ABI
from stake_watch.models.common import Chain, PositionType
from stake_watch.models.position import Position
from stake_watch.models.protocol import ProtocolStats

class CompoundV3Collector(BaseCollector):
    def __init__(self, chain: Chain, protocol: str, comet_address: str, rpc_url: str):
        super().__init__(chain=chain, protocol=protocol)
        self.comet_address = comet_address
        self.rpc_url = rpc_url

    def _get_comet_contract(self):
        w3 = AsyncWeb3(AsyncHTTPProvider(self.rpc_url))
        return w3.eth.contract(address=w3.to_checksum_address(self.comet_address), abi=COMET_ABI)

    async def collect_positions(self, wallet: str) -> list[Position]:
        comet = self._get_comet_contract()
        scale = Decimal(10**6)
        supply = Decimal(await comet.functions.balanceOf(wallet).call()) / scale
        borrow = Decimal(await comet.functions.borrowBalanceOf(wallet).call()) / scale
        positions = []
        if supply > 0:
            positions.append(Position(chain=self.chain, protocol=self.protocol, wallet=wallet,
                asset="USDC", position_type=PositionType.SUPPLY, amount=supply,
                value_usd=supply, apy=0.0, updated_at=datetime.now(timezone.utc)))
        if borrow > 0:
            positions.append(Position(chain=self.chain, protocol=self.protocol, wallet=wallet,
                asset="USDC", position_type=PositionType.BORROW, amount=borrow,
                value_usd=borrow, apy=0.0, updated_at=datetime.now(timezone.utc)))
        return positions

    async def collect_protocol_stats(self) -> ProtocolStats:
        return ProtocolStats(chain=self.chain, protocol=self.protocol,
            tvl_usd=Decimal("0"), pools=[], updated_at=datetime.now(timezone.utc))
