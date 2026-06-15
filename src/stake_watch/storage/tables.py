from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, Numeric, String, Float, Text
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
