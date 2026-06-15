from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from stake_watch.models.common import Chain, PositionType
from stake_watch.models.position import Position
from stake_watch.models.protocol import PoolStats, ProtocolStats
from stake_watch.storage.tables import Base, PositionRow, ProtocolStatsRow


class Storage:
    def __init__(self, db_url: str):
        self._engine = create_async_engine(db_url, echo=False)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    async def initialize(self):
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self):
        await self._engine.dispose()

    async def save_positions(self, positions: list[Position]):
        async with self._session_factory() as session:
            for pos in positions:
                existing = await session.execute(
                    select(PositionRow).where(
                        PositionRow.wallet == pos.wallet,
                        PositionRow.protocol == pos.protocol,
                        PositionRow.asset == pos.asset,
                        PositionRow.position_type == pos.position_type.value,
                    )
                )
                row = existing.scalar_one_or_none()
                if row:
                    row.chain = pos.chain.value
                    row.amount = pos.amount
                    row.value_usd = pos.value_usd
                    row.apy = pos.apy
                    row.ltv = pos.ltv
                    row.health_factor = pos.health_factor
                    row.vault_version = pos.vault_version
                    row.updated_at = pos.updated_at
                else:
                    row = PositionRow(
                        chain=pos.chain.value,
                        protocol=pos.protocol,
                        wallet=pos.wallet,
                        asset=pos.asset,
                        position_type=pos.position_type.value,
                        amount=pos.amount,
                        value_usd=pos.value_usd,
                        apy=pos.apy,
                        ltv=pos.ltv,
                        health_factor=pos.health_factor,
                        vault_version=pos.vault_version,
                        updated_at=pos.updated_at,
                    )
                    session.add(row)
            await session.commit()

    async def get_latest_positions(self, wallet: str) -> list[Position]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(PositionRow).where(PositionRow.wallet == wallet)
            )
            rows = result.scalars().all()
            return [
                Position(
                    chain=Chain(r.chain),
                    protocol=r.protocol,
                    wallet=r.wallet,
                    asset=r.asset,
                    position_type=PositionType(r.position_type),
                    amount=r.amount,
                    value_usd=r.value_usd,
                    apy=r.apy,
                    ltv=r.ltv,
                    health_factor=r.health_factor,
                    vault_version=r.vault_version,
                    updated_at=r.updated_at,
                )
                for r in rows
            ]

    async def save_protocol_stats(self, stats: ProtocolStats):
        pools_json = json.dumps(
            [p.model_dump(mode="json") for p in stats.pools]
        )
        async with self._session_factory() as session:
            existing = await session.execute(
                select(ProtocolStatsRow).where(
                    ProtocolStatsRow.protocol == stats.protocol
                )
            )
            row = existing.scalar_one_or_none()
            if row:
                row.chain = stats.chain.value
                row.tvl_usd = stats.tvl_usd
                row.pools_json = pools_json
                row.updated_at = stats.updated_at
            else:
                row = ProtocolStatsRow(
                    chain=stats.chain.value,
                    protocol=stats.protocol,
                    tvl_usd=stats.tvl_usd,
                    pools_json=pools_json,
                    updated_at=stats.updated_at,
                )
                session.add(row)
            await session.commit()

    async def get_latest_protocol_stats(self, protocol: str) -> ProtocolStats | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ProtocolStatsRow).where(
                    ProtocolStatsRow.protocol == protocol
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                return None
            pools = [PoolStats.model_validate(p) for p in json.loads(row.pools_json)]
            return ProtocolStats(
                chain=Chain(row.chain),
                protocol=row.protocol,
                tvl_usd=row.tvl_usd,
                pools=pools,
                updated_at=row.updated_at,
            )
