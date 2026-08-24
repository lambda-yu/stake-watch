from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from stake_watch.collectors.base import BaseCollector
from stake_watch.collectors.morpho.morpho_api import fetch_vault_data
from stake_watch.models.common import Chain
from stake_watch.models.position import Position
from stake_watch.models.protocol import PoolStats, ProtocolStats

class MorphoCollector(BaseCollector):
    def __init__(self, chain: Chain, protocol: str, vault_address: str,
                 morpho_address: str, rpc_url: str):
        super().__init__(chain=chain, protocol=protocol)
        self.vault_address = vault_address
        self.morpho_address = morpho_address
        self.rpc_url = rpc_url

    async def collect_positions(self, wallet: str) -> list[Position]:
        return []

    async def collect_protocol_stats(self) -> ProtocolStats:
        chain_str = self.chain.value if hasattr(self.chain, "value") else str(self.chain)
        vd = await fetch_vault_data(self.vault_address, chain_str)
        if not vd:
            raise RuntimeError(
                f"Morpho GraphQL API returned no data for vault {self.vault_address}")
        tvl = Decimal(str(vd["tvl_usd"]))
        pool = PoolStats(
            pool_id=self.vault_address,
            asset=vd["asset"],
            supply_apy=vd["apy"],
            borrow_apy=0.0,
            total_supply=tvl,
            total_borrow=Decimal("0"),
            utilization=float(vd.get("utilization") or 0))
        return ProtocolStats(
            chain=self.chain, protocol=self.protocol,
            tvl_usd=tvl,
            pools=[pool], updated_at=datetime.now(timezone.utc))
