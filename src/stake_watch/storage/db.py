from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from stake_watch.models.common import Chain, PositionType
from stake_watch.models.position import Position
from stake_watch.models.protocol import PoolStats, ProtocolStats
from stake_watch.storage.tables import Base, PositionRow, ProtocolStatsRow, AlertRow
from stake_watch.models.alert import Alert as AlertModel, RuleType, Severity


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

    async def save_alert(self, alert):
        async with self._session_factory() as session:
            row = AlertRow(
                rule_type=alert.rule_type.value,
                severity=alert.severity.value,
                protocol=alert.protocol,
                chain=alert.chain,
                title=alert.title,
                message=alert.message,
                details_json=json.dumps(alert.details) if alert.details else None,
                dedup_key=alert.dedup_key,
                created_at=alert.created_at,
            )
            session.add(row)
            await session.commit()

    async def get_recent_alerts(self, limit: int = 50):
        async with self._session_factory() as session:
            result = await session.execute(
                select(AlertRow).order_by(AlertRow.created_at.desc()).limit(limit)
            )
            rows = result.scalars().all()
            return [
                AlertModel(
                    rule_type=RuleType(r.rule_type),
                    severity=Severity(r.severity),
                    protocol=r.protocol,
                    chain=r.chain,
                    title=r.title,
                    message=r.message,
                    details=json.loads(r.details_json) if r.details_json else None,
                    created_at=r.created_at,
                )
                for r in rows
            ]

    async def save_stablecoin_snapshot(self, snapshot):
        import json
        from stake_watch.storage.tables import StablecoinMetricsRow
        async with self._session_factory() as session:
            row = StablecoinMetricsRow(
                token=snapshot.token, price=snapshot.price, deviation=snapshot.deviation,
                total_supply=snapshot.total_supply,
                supply_change_24h_pct=snapshot.supply_change_24h_pct,
                supply_change_7d_pct=snapshot.supply_change_7d_pct,
                risk_level=snapshot.risk_level,
                chain_data_json=json.dumps([]),
                updated_at=snapshot.updated_at)
            session.add(row)
            await session.commit()

    async def get_latest_stablecoin_snapshots(self) -> list:
        import json
        from sqlalchemy import func
        from stake_watch.storage.tables import StablecoinMetricsRow
        from stake_watch.models.stablecoin import StablecoinRiskSnapshot
        async with self._session_factory() as session:
            # Get latest snapshot per token
            subq = select(
                StablecoinMetricsRow.token,
                func.max(StablecoinMetricsRow.id).label("max_id")
            ).group_by(StablecoinMetricsRow.token).subquery()
            result = await session.execute(
                select(StablecoinMetricsRow).join(
                    subq, StablecoinMetricsRow.id == subq.c.max_id))
            rows = result.scalars().all()
            return [StablecoinRiskSnapshot(
                token=r.token, price=r.price, deviation=r.deviation,
                total_supply=r.total_supply,
                supply_change_24h_pct=r.supply_change_24h_pct,
                supply_change_7d_pct=r.supply_change_7d_pct,
                risk_level=r.risk_level,
                updated_at=r.updated_at) for r in rows]
