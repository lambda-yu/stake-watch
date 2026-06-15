from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Numeric, String, Float, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PositionRow(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chain: Mapped[str] = mapped_column(String(20))
    protocol: Mapped[str] = mapped_column(String(100))
    wallet: Mapped[str] = mapped_column(String(100))
    asset: Mapped[str] = mapped_column(String(20))
    position_type: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    value_usd: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    apy: Mapped[float] = mapped_column(Float)
    ltv: Mapped[float | None] = mapped_column(Float, nullable=True)
    health_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    vault_version: Mapped[str | None] = mapped_column(String(10), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_positions_wallet_protocol_asset", "wallet", "protocol", "asset", "position_type", unique=True),
    )


class ProtocolStatsRow(Base):
    __tablename__ = "protocol_stats"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chain: Mapped[str] = mapped_column(String(20))
    protocol: Mapped[str] = mapped_column(String(100))
    tvl_usd: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    pools_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_protocol_stats_protocol", "protocol", unique=True),
    )


class WalletRow(Base):
    __tablename__ = "wallets"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chain: Mapped[str] = mapped_column(String(20))
    address: Mapped[str] = mapped_column(String(100))
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RpcEndpointRow(Base):
    __tablename__ = "rpc_endpoints"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chain: Mapped[str] = mapped_column(String(20), unique=True)
    primary_url: Mapped[str] = mapped_column(String(500))
    fallback_urls: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProtocolConfigRow(Base):
    __tablename__ = "protocol_configs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    chain: Mapped[str] = mapped_column(String(20))
    collector: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    safety_rank: Mapped[int | None] = mapped_column(nullable=True)
    safety_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_apy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    primary_risks: Mapped[str] = mapped_column(Text, default="[]")
    vault_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    defillama_slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AppSettingsRow(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AlertRow(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rule_type: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(String(20))
    protocol: Mapped[str] = mapped_column(String(100))
    chain: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedup_key: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StablecoinMetricsRow(Base):
    __tablename__ = "stablecoin_metrics"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(10))
    price: Mapped[float] = mapped_column(Float)
    deviation: Mapped[float] = mapped_column(Float)
    total_supply: Mapped[Decimal] = mapped_column(Numeric(38, 2))
    supply_change_24h_pct: Mapped[float] = mapped_column(Float)
    supply_change_7d_pct: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[str] = mapped_column(String(20))
    chain_data_json: Mapped[str] = mapped_column(Text, default="[]")
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    hard_trigger: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cex_spread_pct: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_stablecoin_token", "token"),)
