from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
import httpx
from stake_watch.collectors.base import BaseCollector
from stake_watch.models.common import Chain
from stake_watch.models.position import Position
from stake_watch.models.protocol import PoolStats, ProtocolStats

YIELDS_URL = "https://yields.llama.fi/pools"

class DefiLlamaCollector(BaseCollector):
    def __init__(self, chain: Chain, protocol: str, defillama_slug: str,
                 chain_filter: str, pool_filter: str | None = None):
        super().__init__(chain=chain, protocol=protocol)
        self.defillama_slug = defillama_slug
        self.chain_filter = chain_filter
        self.pool_filter = pool_filter

    async def collect_positions(self, wallet: str) -> list[Position]:
        return []

    async def collect_protocol_stats(self) -> ProtocolStats:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(YIELDS_URL)
            resp.raise_for_status()
            data = resp.json()
        pools_raw = data.get("data", [])
        filtered = [p for p in pools_raw
            if p.get("project") == self.defillama_slug and p.get("chain") == self.chain_filter]

        if self.pool_filter:
            f = self.pool_filter.upper()
            filtered = [p for p in filtered
                if f in (p.get("symbol") or "").upper()
                or f in (p.get("poolMeta") or "").upper()
                or f == (p.get("pool") or "").lower()]
        else:
            stable_filtered = [p for p in filtered
                if "USDC" in (p.get("symbol") or "").upper()
                or "USDT" in (p.get("symbol") or "").upper()]
            if stable_filtered:
                filtered = stable_filtered

        pools = []
        total_tvl = Decimal("0")
        for p in filtered:
            tvl = Decimal(str(p.get("tvlUsd", 0)))
            total_tvl += tvl
            pools.append(PoolStats(pool_id=p.get("pool", "unknown"), asset=p.get("symbol", "unknown"),
                supply_apy=p.get("apy", 0) or 0, borrow_apy=0, total_supply=tvl,
                total_borrow=Decimal("0"), utilization=0))
        return ProtocolStats(chain=self.chain, protocol=self.protocol, tvl_usd=total_tvl,
            pools=pools, updated_at=datetime.now(timezone.utc))
