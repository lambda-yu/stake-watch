from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from stake_watch.collectors.base import BaseCollector
from stake_watch.models.common import Chain
from stake_watch.models.position import Position
from stake_watch.models.protocol import ProtocolStats

class KaminoCollector(BaseCollector):
    def __init__(self, chain: Chain, protocol: str, rpc_url: str):
        super().__init__(chain=chain, protocol=protocol)
        self.rpc_url = rpc_url

    async def collect_positions(self, wallet: str) -> list[Position]:
        return []

    async def collect_protocol_stats(self) -> ProtocolStats:
        return ProtocolStats(chain=self.chain, protocol=self.protocol,
            tvl_usd=Decimal("0"), pools=[], updated_at=datetime.now(timezone.utc))
