# Stake Watch P1a: Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the working backend foundation — config (DB-stored), data models, SQLite storage, BaseCollector, DefiLlama collector, scheduler — so the tool can collect and persist real DeFi protocol data on a schedule. Config is stored in DB and seeded from `config/seed.yaml` on first startup. The frontend config UI is in P1b.

**Architecture:** Python async application using `uv` for dependency management, Pydantic models for data, SQLAlchemy + SQLite for persistence, APScheduler for cron-style collection. Config is DB-stored (not YAML) with seed.yaml for first-time initialization. FastAPI app and React frontend are in P1b.

**Tech Stack:** Python 3.12+, uv, pydantic, pydantic-settings, SQLAlchemy 2.0 (async), aiosqlite, httpx, APScheduler, PyYAML, pytest, pytest-asyncio

**Note:** This is P1a. P1b (FastAPI config API + React frontend) follows immediately after.

---

## Chunk 1: Project Skeleton & Config

### Task 1: Initialize project with uv

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `.gitignore`
- Create: `src/stake_watch/__init__.py`

- [ ] **Step 1: Initialize uv project**

```bash
cd /Users/user/yu/code/stake-watch
uv init --lib --name stake-watch
```

If uv init doesn't produce the right structure, manually create:

```toml
# pyproject.toml
[project]
name = "stake-watch"
version = "0.1.0"
description = "Cross-chain DeFi yield monitoring and risk alerting"
requires-python = ">=3.12"
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/stake_watch"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

```
# .python-version
3.12
```

- [ ] **Step 2: Add core dependencies**

```bash
uv add pydantic pydantic-settings pyyaml httpx sqlalchemy aiosqlite apscheduler python-dotenv
uv add --dev pytest pytest-asyncio pytest-cov
```

- [ ] **Step 3: Create .gitignore**

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
.venv/

# Secrets
.env
config/settings.local.yaml

# Database
*.db
*.db-journal
*.db-wal

# IDE
.idea/
.vscode/
*.swp
```

- [ ] **Step 4: Create package init**

```bash
mkdir -p src/stake_watch
touch src/stake_watch/__init__.py
```

- [ ] **Step 5: Verify project builds**

```bash
uv run python -c "import stake_watch; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .python-version .gitignore src/ uv.lock
git commit -m "feat: initialize project skeleton with uv"
```

---

### Task 2: Config system with Pydantic Settings

**Files:**
- Create: `src/stake_watch/config.py`
- Create: `config/settings.yaml`
- Create: `config/settings.example.yaml`
- Create: `config/protocols.yaml`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for config loading**

```python
# tests/test_config.py
import os
from pathlib import Path

import pytest

from stake_watch.config import (
    AppSettings,
    ProtocolEntry,
    load_settings,
    load_protocols,
)


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    settings_yaml = tmp_path / "settings.yaml"
    settings_yaml.write_text(
        """
wallets:
  - chain: base
    address: "0xTestWallet"

rpc:
  base:
    primary: "https://mainnet.base.org"
    fallback: []

database:
  url: "sqlite:///test.db"

intervals:
  positions: 300
  protocol_stats: 900
  stablecoin_price: 60
  stablecoin_supply: 600
  reserves: 21600
"""
    )
    protocols_yaml = tmp_path / "protocols.yaml"
    protocols_yaml.write_text(
        """
protocols:
  - name: aave_v3_base
    chain: base
    collector: base_chain.aave_base
    enabled: true
    safety_score: 8.8
    primary_risks:
      - "shared pool bad debt"
"""
    )
    return tmp_path


def test_load_settings(config_dir: Path):
    settings = load_settings(config_dir / "settings.yaml")
    assert len(settings.wallets) == 1
    assert settings.wallets[0].chain == "base"
    assert settings.wallets[0].address == "0xTestWallet"
    assert settings.rpc["base"].primary == "https://mainnet.base.org"
    assert settings.database.url == "sqlite:///test.db"
    assert settings.intervals.positions == 300


def test_load_protocols(config_dir: Path):
    protocols = load_protocols(config_dir / "protocols.yaml")
    assert len(protocols) == 1
    assert protocols[0].name == "aave_v3_base"
    assert protocols[0].chain == "base"
    assert protocols[0].enabled is True
    assert protocols[0].safety_score == 8.8


def test_settings_has_defaults():
    """Settings should provide sensible defaults when YAML is minimal."""
    settings = load_settings(None)
    assert settings.intervals.positions == 300
    assert settings.intervals.protocol_stats == 900


def test_local_override(config_dir: Path):
    """settings.local.yaml should override base settings."""
    local = config_dir / "settings.local.yaml"
    local.write_text(
        """
wallets:
  - chain: ethereum
    address: "0xRealWallet"
"""
    )
    settings = load_settings(config_dir / "settings.yaml", local_path=local)
    assert settings.wallets[0].chain == "ethereum"
    assert settings.wallets[0].address == "0xRealWallet"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'stake_watch.config'`

- [ ] **Step 3: Implement config module**

```python
# src/stake_watch/config.py
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel


class WalletConfig(BaseModel):
    chain: str
    address: str


class RpcEndpoint(BaseModel):
    primary: str
    fallback: list[str] = []


class DatabaseConfig(BaseModel):
    url: str = "sqlite:///stake_watch.db"


class IntervalConfig(BaseModel):
    positions: int = 300
    protocol_stats: int = 900
    stablecoin_price: int = 60
    stablecoin_supply: int = 600
    reserves: int = 21600


class RiskConfig(BaseModel):
    liquidation_warning: float = 1.3
    liquidation_critical: float = 1.1
    depeg_warning: float = 0.005
    depeg_critical: float = 0.02
    tvl_crash_threshold: float = 0.15
    apy_change_threshold: float = 0.30


class TelegramConfig(BaseModel):
    bot_token: str = ""
    chat_id: str = ""


class AppSettings(BaseModel):
    wallets: list[WalletConfig] = []
    rpc: dict[str, RpcEndpoint] = {}
    database: DatabaseConfig = DatabaseConfig()
    intervals: IntervalConfig = IntervalConfig()
    risk: RiskConfig = RiskConfig()
    telegram: TelegramConfig = TelegramConfig()


class ProtocolEntry(BaseModel):
    name: str
    chain: str
    collector: str
    enabled: bool = True
    safety_rank: int | None = None
    safety_score: float | None = None
    reference_apy: str | None = None
    primary_risks: list[str] = []
    vault_address: str | None = None
    defillama_slug: str | None = None


class ChainConfig(BaseModel):
    """Placeholder for future chain-specific config. Currently unused in P1."""
    pass


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_settings(
    path: Path | None, local_path: Path | None = None
) -> AppSettings:
    data: dict = {}
    if path and path.exists():
        data = yaml.safe_load(path.read_text()) or {}
    if local_path and local_path.exists():
        local_data = yaml.safe_load(local_path.read_text()) or {}
        data = _deep_merge(data, local_data)
    return AppSettings.model_validate(data)


def load_protocols(path: Path) -> list[ProtocolEntry]:
    raw = yaml.safe_load(path.read_text()) or {}
    entries = raw.get("protocols", [])
    return [ProtocolEntry.model_validate(e) for e in entries]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: All 4 tests PASS

- [ ] **Step 5: Create settings.example.yaml**

```yaml
# config/settings.example.yaml
# Copy to settings.local.yaml and fill in real values

wallets:
  - chain: solana
    address: "<your-solana-wallet>"
  - chain: ethereum
    address: "<your-eth-wallet>"
  - chain: base
    address: "<your-base-wallet>"
  - chain: bsc
    address: "<your-bsc-wallet>"

rpc:
  solana:
    primary: "https://api.mainnet-beta.solana.com"
    fallback: []
  ethereum:
    primary: "https://eth.public-rpc.com"
    fallback: []
  base:
    primary: "https://mainnet.base.org"
    fallback: []
  bsc:
    primary: "https://bsc-dataseed.binance.org"
    fallback: []

database:
  url: "sqlite:///stake_watch.db"

telegram:
  bot_token: "${TELEGRAM_BOT_TOKEN}"
  chat_id: "${TELEGRAM_CHAT_ID}"

intervals:
  positions: 300
  protocol_stats: 900
  stablecoin_price: 60
  stablecoin_supply: 600
  reserves: 21600

risk:
  liquidation_warning: 1.3
  liquidation_critical: 1.1
  depeg_warning: 0.005
  depeg_critical: 0.02
  tvl_crash_threshold: 0.15
  apy_change_threshold: 0.30
```

```yaml
# config/settings.yaml
# Base settings (committed to git). Override secrets in settings.local.yaml.

wallets: []

rpc:
  base:
    primary: "https://mainnet.base.org"
    fallback: []
  ethereum:
    primary: "https://eth.public-rpc.com"
    fallback: []
  solana:
    primary: "https://api.mainnet-beta.solana.com"
    fallback: []
  bsc:
    primary: "https://bsc-dataseed.binance.org"
    fallback: []

database:
  url: "sqlite:///stake_watch.db"

intervals:
  positions: 300
  protocol_stats: 900
  stablecoin_price: 60
  stablecoin_supply: 600
  reserves: 21600

risk:
  liquidation_warning: 1.3
  liquidation_critical: 1.1
  depeg_warning: 0.005
  depeg_critical: 0.02
  tvl_crash_threshold: 0.15
  apy_change_threshold: 0.30
```

```yaml
# config/protocols.yaml
protocols:
  - name: aave_v3_base
    chain: base
    collector: base_chain.aave_base
    safety_rank: 1
    reference_apy: "~3.17%"
    safety_score: 8.8
    primary_risks: ["shared pool bad debt", "utilization", "Base L2 risk"]
    enabled: true

  - name: morpho_steakhouse_usdc
    chain: base
    collector: morpho.chain_base
    vault_address: "<steakhouse-vault>"
    safety_rank: 3
    reference_apy: "~3.5-4.0%"
    safety_score: 8.3
    primary_risks: ["curator risk", "underlying market bad debt"]
    enabled: true

  - name: jupiter_lend
    chain: solana
    collector: solana.jupiter_lend
    safety_rank: 9
    reference_apy: "~4.0-4.25%"
    safety_score: 7.2
    primary_risks: ["newer protocol", "unified liquidity", "withdrawal smoothing"]
    enabled: true
```

- [ ] **Step 6: Commit**

```bash
git add src/stake_watch/config.py tests/test_config.py config/
git commit -m "feat: add config system with YAML loading and local overrides"
```

---

## Chunk 2: Data Models & Storage

### Task 3: Core data models (Pydantic)

**Files:**
- Create: `src/stake_watch/models/__init__.py`
- Create: `src/stake_watch/models/common.py`
- Create: `src/stake_watch/models/position.py`
- Create: `src/stake_watch/models/protocol.py`
- Test: `tests/models/test_position.py`
- Test: `tests/models/test_protocol.py`

- [ ] **Step 1: Write failing tests for Position model**

```python
# tests/models/__init__.py
# (empty)
```

```python
# tests/models/test_position.py
from datetime import datetime, timezone
from decimal import Decimal

from stake_watch.models.common import Chain, PositionType
from stake_watch.models.position import Position


def test_position_creation():
    pos = Position(
        chain=Chain.BASE,
        protocol="aave_v3_base",
        wallet="0xTestWallet",
        asset="USDC",
        position_type=PositionType.SUPPLY,
        amount=Decimal("10000.00"),
        value_usd=Decimal("10000.00"),
        apy=3.17,
        ltv=None,
        health_factor=None,
        vault_version=None,
        updated_at=datetime.now(timezone.utc),
    )
    assert pos.chain == Chain.BASE
    assert pos.position_type == PositionType.SUPPLY
    assert pos.amount == Decimal("10000.00")


def test_position_with_vault():
    pos = Position(
        chain=Chain.BASE,
        protocol="morpho_steakhouse_usdc",
        wallet="0xTestWallet",
        asset="USDC",
        position_type=PositionType.VAULT,
        amount=Decimal("5000.00"),
        value_usd=Decimal("5000.00"),
        apy=3.8,
        ltv=None,
        health_factor=None,
        vault_version="v1.1",
        updated_at=datetime.now(timezone.utc),
    )
    assert pos.vault_version == "v1.1"
    assert pos.position_type == PositionType.VAULT
```

```python
# tests/models/test_protocol.py
from datetime import datetime, timezone
from decimal import Decimal

from stake_watch.models.common import Chain
from stake_watch.models.protocol import PoolStats, ProtocolStats


def test_protocol_stats():
    stats = ProtocolStats(
        chain=Chain.BASE,
        protocol="aave_v3_base",
        tvl_usd=Decimal("500000000"),
        pools=[
            PoolStats(
                pool_id="usdc-main",
                asset="USDC",
                supply_apy=3.17,
                borrow_apy=5.2,
                total_supply=Decimal("300000000"),
                total_borrow=Decimal("200000000"),
                utilization=0.667,
            )
        ],
        updated_at=datetime.now(timezone.utc),
    )
    assert stats.tvl_usd == Decimal("500000000")
    assert len(stats.pools) == 1
    assert stats.pools[0].utilization == 0.667
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/models/ -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement models**

```python
# src/stake_watch/models/__init__.py
from stake_watch.models.common import Chain, PositionType
from stake_watch.models.position import Position
from stake_watch.models.protocol import PoolStats, ProtocolStats

__all__ = ["Chain", "PositionType", "Position", "PoolStats", "ProtocolStats"]
```

```python
# src/stake_watch/models/common.py
from enum import Enum


class Chain(str, Enum):
    SOLANA = "solana"
    ETHEREUM = "ethereum"
    BSC = "bsc"
    BASE = "base"


class PositionType(str, Enum):
    SUPPLY = "supply"
    BORROW = "borrow"
    STAKE = "stake"
    LP = "lp"
    VAULT = "vault"
```

```python
# src/stake_watch/models/position.py
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from stake_watch.models.common import Chain, PositionType


class Position(BaseModel):
    chain: Chain
    protocol: str
    wallet: str
    asset: str
    position_type: PositionType
    amount: Decimal
    value_usd: Decimal
    apy: float
    ltv: float | None = None
    health_factor: float | None = None
    vault_version: str | None = None
    updated_at: datetime
```

```python
# src/stake_watch/models/protocol.py
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from stake_watch.models.common import Chain


class PoolStats(BaseModel):
    pool_id: str
    asset: str
    supply_apy: float
    borrow_apy: float
    total_supply: Decimal
    total_borrow: Decimal
    utilization: float


class ProtocolStats(BaseModel):
    chain: Chain
    protocol: str
    tvl_usd: Decimal
    pools: list[PoolStats] = []
    updated_at: datetime
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/models/ -v
```

Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/stake_watch/models/ tests/models/
git commit -m "feat: add core data models (Position, ProtocolStats, Chain, PositionType)"
```

---

### Task 4: SQLite storage layer

**Files:**
- Create: `src/stake_watch/storage/__init__.py`
- Create: `src/stake_watch/storage/db.py`
- Create: `src/stake_watch/storage/tables.py`
- Test: `tests/storage/test_db.py`

- [ ] **Step 1: Write failing tests for storage**

```python
# tests/storage/__init__.py
# (empty)
```

```python
# tests/storage/test_db.py
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from stake_watch.models.common import Chain, PositionType
from stake_watch.models.position import Position
from stake_watch.models.protocol import PoolStats, ProtocolStats
from stake_watch.storage.db import Storage


@pytest.fixture
async def storage(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    s = Storage(db_url)
    await s.initialize()
    yield s
    await s.close()


@pytest.mark.asyncio
async def test_save_and_get_positions(storage: Storage):
    pos = Position(
        chain=Chain.BASE,
        protocol="aave_v3_base",
        wallet="0xTest",
        asset="USDC",
        position_type=PositionType.SUPPLY,
        amount=Decimal("10000"),
        value_usd=Decimal("10000"),
        apy=3.17,
        updated_at=datetime.now(timezone.utc),
    )
    await storage.save_positions([pos])
    results = await storage.get_latest_positions(wallet="0xTest")
    assert len(results) == 1
    assert results[0].protocol == "aave_v3_base"
    assert results[0].amount == Decimal("10000")


@pytest.mark.asyncio
async def test_save_and_get_protocol_stats(storage: Storage):
    stats = ProtocolStats(
        chain=Chain.BASE,
        protocol="aave_v3_base",
        tvl_usd=Decimal("500000000"),
        pools=[
            PoolStats(
                pool_id="usdc",
                asset="USDC",
                supply_apy=3.17,
                borrow_apy=5.2,
                total_supply=Decimal("300000000"),
                total_borrow=Decimal("200000000"),
                utilization=0.667,
            )
        ],
        updated_at=datetime.now(timezone.utc),
    )
    await storage.save_protocol_stats(stats)
    result = await storage.get_latest_protocol_stats("aave_v3_base")
    assert result is not None
    assert result.tvl_usd == Decimal("500000000")


@pytest.mark.asyncio
async def test_positions_upsert(storage: Storage):
    """Saving same position twice should update, not duplicate."""
    now = datetime.now(timezone.utc)
    pos1 = Position(
        chain=Chain.BASE, protocol="aave_v3_base", wallet="0xTest",
        asset="USDC", position_type=PositionType.SUPPLY,
        amount=Decimal("10000"), value_usd=Decimal("10000"),
        apy=3.0, updated_at=now,
    )
    pos2 = Position(
        chain=Chain.BASE, protocol="aave_v3_base", wallet="0xTest",
        asset="USDC", position_type=PositionType.SUPPLY,
        amount=Decimal("15000"), value_usd=Decimal("15000"),
        apy=3.5, updated_at=now,
    )
    await storage.save_positions([pos1])
    await storage.save_positions([pos2])
    results = await storage.get_latest_positions(wallet="0xTest")
    assert len(results) == 1
    assert results[0].amount == Decimal("15000")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/storage/ -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement storage**

```python
# src/stake_watch/storage/__init__.py
from stake_watch.storage.db import Storage

__all__ = ["Storage"]
```

```python
# src/stake_watch/storage/tables.py
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
```

```python
# src/stake_watch/storage/db.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/storage/ -v
```

Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/stake_watch/storage/ src/stake_watch/models/ tests/storage/
git commit -m "feat: add SQLite storage layer with position upsert and protocol stats"
```

---

## Chunk 3: BaseCollector & DefiLlama Collector

### Task 5: BaseCollector abstract base class

**Files:**
- Create: `src/stake_watch/collectors/__init__.py`
- Create: `src/stake_watch/collectors/base.py`
- Test: `tests/collectors/test_base.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/collectors/__init__.py
# (empty)
```

```python
# tests/collectors/test_base.py
import pytest

from stake_watch.collectors.base import BaseCollector, CollectResult
from stake_watch.models.common import Chain


def test_base_collector_is_abstract():
    with pytest.raises(TypeError):
        BaseCollector(chain=Chain.BASE, protocol="test")


def test_collect_result_creation():
    result = CollectResult(positions=[], protocol_stats=None, errors=[])
    assert result.positions == []
    assert result.protocol_stats is None
    assert result.errors == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/collectors/test_base.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement BaseCollector**

```python
# src/stake_watch/collectors/__init__.py
from stake_watch.collectors.base import BaseCollector, CollectResult

__all__ = ["BaseCollector", "CollectResult"]
```

```python
# src/stake_watch/collectors/base.py
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from pydantic import BaseModel

from stake_watch.models.common import Chain
from stake_watch.models.position import Position
from stake_watch.models.protocol import ProtocolStats

logger = logging.getLogger(__name__)


class CollectResult(BaseModel):
    positions: list[Position] = []
    protocol_stats: ProtocolStats | None = None
    errors: list[str] = []


class BaseCollector(ABC):
    def __init__(self, chain: Chain, protocol: str):
        self.chain = chain
        self.protocol = protocol
        self.logger = logging.getLogger(f"collector.{protocol}")

    @abstractmethod
    async def collect_positions(self, wallet: str) -> list[Position]: ...

    @abstractmethod
    async def collect_protocol_stats(self) -> ProtocolStats: ...

    async def collect(self, wallet: str) -> CollectResult:
        errors: list[str] = []
        positions: list[Position] = []
        protocol_stats: ProtocolStats | None = None

        try:
            positions = await self.collect_positions(wallet)
        except Exception as e:
            msg = f"{self.protocol}: positions collection failed: {e}"
            self.logger.error(msg)
            errors.append(msg)

        try:
            protocol_stats = await self.collect_protocol_stats()
        except Exception as e:
            msg = f"{self.protocol}: stats collection failed: {e}"
            self.logger.error(msg)
            errors.append(msg)

        return CollectResult(
            positions=positions,
            protocol_stats=protocol_stats,
            errors=errors,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/collectors/test_base.py -v
```

Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/stake_watch/collectors/ tests/collectors/
git commit -m "feat: add BaseCollector abstract class with error-isolated collect()"
```

---

### Task 6: DefiLlama collector

This is the first real collector — it fetches TVL, APY, and pool data from DefiLlama's free API. No RPC needed, proving the full pipeline.

**Files:**
- Create: `src/stake_watch/collectors/defillama.py`
- Test: `tests/collectors/test_defillama.py`

**DefiLlama API endpoints used:**
- `GET https://yields.llama.fi/pools` — all yield pools (APY, TVL per pool)
- `GET https://api.llama.fi/protocol/{slug}` — protocol TVL

- [ ] **Step 1: Write failing tests with mocked HTTP responses**

```python
# tests/collectors/test_defillama.py
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from stake_watch.collectors.defillama import DefiLlamaCollector
from stake_watch.models.common import Chain


@pytest.fixture
def collector():
    return DefiLlamaCollector(
        chain=Chain.BASE,
        protocol="aave_v3_base",
        defillama_slug="aave-v3",
        chain_filter="Base",
    )


MOCK_POOLS_RESPONSE = {
    "data": [
        {
            "pool": "pool-id-1",
            "chain": "Base",
            "project": "aave-v3",
            "symbol": "USDC",
            "tvlUsd": 300000000,
            "apy": 3.17,
            "apyBase": 3.17,
            "apyReward": 0,
        },
        {
            "pool": "pool-id-2",
            "chain": "Base",
            "project": "aave-v3",
            "symbol": "WETH",
            "tvlUsd": 200000000,
            "apy": 1.5,
            "apyBase": 1.5,
            "apyReward": 0,
        },
        {
            "pool": "pool-id-3",
            "chain": "Ethereum",
            "project": "aave-v3",
            "symbol": "USDC",
            "tvlUsd": 500000000,
            "apy": 4.0,
            "apyBase": 4.0,
            "apyReward": 0,
        },
    ]
}


@pytest.mark.asyncio
async def test_collect_protocol_stats(collector: DefiLlamaCollector):
    async def fake_get(*args, **kwargs):
        resp = MagicMock()
        resp.json = MagicMock(return_value=MOCK_POOLS_RESPONSE)
        resp.raise_for_status = MagicMock(return_value=None)
        return resp

    with patch("httpx.AsyncClient.get", new=fake_get):
        stats = await collector.collect_protocol_stats()

    assert stats.protocol == "aave_v3_base"
    assert stats.chain == Chain.BASE
    assert len(stats.pools) >= 1
    usdc_pool = next(p for p in stats.pools if p.asset == "USDC")
    assert usdc_pool.supply_apy == 3.17


@pytest.mark.asyncio
async def test_chain_filter_applied(collector: DefiLlamaCollector):
    """Only Base chain pools should be included."""
    async def fake_get(*args, **kwargs):
        resp = MagicMock()
        resp.json = MagicMock(return_value=MOCK_POOLS_RESPONSE)
        resp.raise_for_status = MagicMock(return_value=None)
        return resp

    with patch("httpx.AsyncClient.get", new=fake_get):
        stats = await collector.collect_protocol_stats()

    assert stats.chain == Chain.BASE
    # Ethereum pool should be filtered out — only 2 Base pools
    assert len(stats.pools) == 2
    assert all(p.pool_id.startswith("pool-id-") for p in stats.pools)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/collectors/test_defillama.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement DefiLlama collector**

```python
# src/stake_watch/collectors/defillama.py
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
    def __init__(
        self,
        chain: Chain,
        protocol: str,
        defillama_slug: str,
        chain_filter: str,
    ):
        super().__init__(chain=chain, protocol=protocol)
        self.defillama_slug = defillama_slug
        self.chain_filter = chain_filter

    async def collect_positions(self, wallet: str) -> list[Position]:
        # DefiLlama doesn't provide per-wallet positions — return empty.
        # Real position data comes from on-chain collectors.
        return []

    async def collect_protocol_stats(self) -> ProtocolStats:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(YIELDS_URL)
            resp.raise_for_status()
            data = resp.json()

        pools_raw = data.get("data", [])
        filtered = [
            p for p in pools_raw
            if p.get("project") == self.defillama_slug
            and p.get("chain") == self.chain_filter
        ]

        pools = []
        total_tvl = Decimal("0")
        for p in filtered:
            tvl = Decimal(str(p.get("tvlUsd", 0)))
            total_tvl += tvl
            pools.append(
                PoolStats(
                    pool_id=p.get("pool", "unknown"),
                    asset=p.get("symbol", "unknown"),
                    supply_apy=p.get("apy", 0) or 0,
                    borrow_apy=0,  # DefiLlama yield endpoint is supply-side
                    total_supply=tvl,
                    total_borrow=Decimal("0"),
                    utilization=0,
                )
            )

        return ProtocolStats(
            chain=self.chain,
            protocol=self.protocol,
            tvl_usd=total_tvl,
            pools=pools,
            updated_at=datetime.now(timezone.utc),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/collectors/test_defillama.py -v
```

Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/stake_watch/collectors/defillama.py tests/collectors/test_defillama.py
git commit -m "feat: add DefiLlama collector for protocol TVL and yield data"
```

---

## Chunk 4: Scheduler & Main Entry Point

### Task 7: Scheduler runner

**Files:**
- Create: `src/stake_watch/scheduler/__init__.py`
- Create: `src/stake_watch/scheduler/runner.py`
- Test: `tests/scheduler/test_runner.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/scheduler/__init__.py
# (empty)
```

```python
# tests/scheduler/test_runner.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stake_watch.collectors.base import CollectResult
from stake_watch.config import AppSettings, IntervalConfig
from stake_watch.models.common import Chain
from stake_watch.scheduler.runner import CollectionRunner


@pytest.fixture
def mock_collector():
    collector = AsyncMock()
    collector.chain = Chain.BASE
    collector.protocol = "test_protocol"
    collector.collect.return_value = CollectResult(
        positions=[], protocol_stats=None, errors=[]
    )
    return collector


@pytest.fixture
def mock_storage():
    storage = AsyncMock()
    return storage


@pytest.mark.asyncio
async def test_run_collection_cycle(mock_collector, mock_storage):
    runner = CollectionRunner(
        collectors=[mock_collector],
        storage=mock_storage,
        wallets=["0xTest"],
    )
    results = await runner.run_collection_cycle()
    assert len(results) == 1
    mock_collector.collect.assert_called_once_with("0xTest")


@pytest.mark.asyncio
async def test_collector_failure_isolated(mock_storage):
    good_collector = AsyncMock()
    good_collector.chain = Chain.BASE
    good_collector.protocol = "good"
    good_collector.collect.return_value = CollectResult(
        positions=[], protocol_stats=None, errors=[]
    )

    bad_collector = AsyncMock()
    bad_collector.chain = Chain.BASE
    bad_collector.protocol = "bad"
    bad_collector.collect.side_effect = Exception("RPC timeout")

    runner = CollectionRunner(
        collectors=[good_collector, bad_collector],
        storage=mock_storage,
        wallets=["0xTest"],
    )
    results = await runner.run_collection_cycle()
    # good_collector should still succeed
    good_collector.collect.assert_called_once()
    assert len(results) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/scheduler/ -v
```

Expected: FAIL

- [ ] **Step 3: Implement runner**

```python
# src/stake_watch/scheduler/__init__.py
from stake_watch.scheduler.runner import CollectionRunner

__all__ = ["CollectionRunner"]
```

```python
# src/stake_watch/scheduler/runner.py
from __future__ import annotations

import asyncio
import logging

from stake_watch.collectors.base import BaseCollector, CollectResult
from stake_watch.storage.db import Storage

logger = logging.getLogger(__name__)


class CollectionRunner:
    def __init__(
        self,
        collectors: list[BaseCollector],
        storage: Storage,
        wallets: list[str],
    ):
        self.collectors = collectors
        self.storage = storage
        self.wallets = wallets

    async def _run_single(
        self, collector: BaseCollector, wallet: str
    ) -> CollectResult:
        try:
            result = await collector.collect(wallet)
            if result.positions:
                await self.storage.save_positions(result.positions)
            if result.protocol_stats:
                await self.storage.save_protocol_stats(result.protocol_stats)
            if result.errors:
                for err in result.errors:
                    logger.warning(err)
            return result
        except Exception as e:
            logger.error(f"{collector.protocol}: unhandled error: {e}")
            return CollectResult(errors=[str(e)])

    async def run_collection_cycle(self) -> list[CollectResult]:
        tasks = []
        for collector in self.collectors:
            for wallet in self.wallets:
                tasks.append(self._run_single(collector, wallet))
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return list(results)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/scheduler/ -v
```

Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/stake_watch/scheduler/ tests/scheduler/
git commit -m "feat: add CollectionRunner with asyncio.gather and failure isolation"
```

---

### Task 8: Main entry point

**Files:**
- Create: `src/stake_watch/main.py`
- Test: `tests/test_main.py` (smoke test)

- [ ] **Step 1: Write failing smoke test**

```python
# tests/test_main.py
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest

from stake_watch.main import build_app


@pytest.mark.asyncio
async def test_build_app_returns_runner(tmp_path: Path):
    db_path = tmp_path / "test.db"
    settings_yaml = tmp_path / "settings.yaml"
    settings_yaml.write_text(f"""
wallets:
  - chain: base
    address: "0xTest"
rpc:
  base:
    primary: "https://mainnet.base.org"
database:
  url: "sqlite+aiosqlite:///{db_path}"
"""
    )
    protocols_yaml = tmp_path / "protocols.yaml"
    protocols_yaml.write_text(
        """
protocols:
  - name: aave_v3_base
    chain: base
    collector: defillama
    enabled: true
"""
    )
    runner, storage, _ = await build_app(
        settings_path=settings_yaml,
        protocols_path=protocols_yaml,
    )
    assert runner is not None
    assert len(runner.collectors) >= 1
    await storage.close()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_main.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement main.py**

```python
# src/stake_watch/main.py
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from stake_watch.collectors.base import BaseCollector
from stake_watch.collectors.defillama import DefiLlamaCollector
from stake_watch.config import AppSettings, ProtocolEntry, load_protocols, load_settings
from stake_watch.models.common import Chain
from stake_watch.scheduler.runner import CollectionRunner
from stake_watch.storage.db import Storage

logger = logging.getLogger(__name__)

DEFILLAMA_CHAIN_MAP = {
    "base": "Base",
    "ethereum": "Ethereum",
    "bsc": "BSC",
    "solana": "Solana",
}

DEFILLAMA_SLUG_MAP = {
    "aave_v3_base": "aave-v3",
    "morpho_steakhouse_usdc": "morpho-blue",
    "morpho_gauntlet_usdc_prime": "morpho-blue",
    "morpho_pangolins_usdc": "morpho-blue",
    "morpho_gauntlet_frontier_usdc": "morpho-blue",
    "jupiter_lend": "jupiter-lend",
    "kamino_usdc": "kamino-lend",
    "compound_v3_usdc": "compound-v3",
    "fluid_usdc": "fluid-lending",
    "sky_susds": "sky",
    "venus_usdc": "venus-core-pool",
}


def _build_collector(entry: ProtocolEntry) -> BaseCollector | None:
    chain = Chain(entry.chain)
    slug = DEFILLAMA_SLUG_MAP.get(entry.name)
    if slug:
        return DefiLlamaCollector(
            chain=chain,
            protocol=entry.name,
            defillama_slug=slug,
            chain_filter=DEFILLAMA_CHAIN_MAP.get(entry.chain, entry.chain),
        )
    logger.warning(f"No collector mapping for {entry.name}, skipping")
    return None


async def build_app(
    settings_path: Path | None = None,
    protocols_path: Path | None = None,
    local_settings_path: Path | None = None,
) -> tuple[CollectionRunner, Storage, AppSettings]:
    settings_path = settings_path or Path("config/settings.yaml")
    protocols_path = protocols_path or Path("config/protocols.yaml")
    local_settings_path = local_settings_path or Path("config/settings.local.yaml")

    settings = load_settings(settings_path, local_path=local_settings_path)
    protocols = load_protocols(protocols_path) if protocols_path.exists() else []

    db_url = settings.database.url
    if not db_url.startswith("sqlite+aiosqlite"):
        db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)

    storage = Storage(db_url)
    await storage.initialize()

    collectors: list[BaseCollector] = []
    for entry in protocols:
        if not entry.enabled:
            continue
        collector = _build_collector(entry)
        if collector:
            collectors.append(collector)

    wallets = [w.address for w in settings.wallets]

    runner = CollectionRunner(
        collectors=collectors,
        storage=storage,
        wallets=wallets or [""],
    )
    return runner, storage, settings


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    runner, storage, settings = await build_app()
    logger.info(
        f"Stake Watch started with {len(runner.collectors)} collectors, "
        f"{len(runner.wallets)} wallets"
    )

    try:
        # Single collection cycle for now; APScheduler integration in next step
        results = await runner.run_collection_cycle()
        for r in results:
            if r.protocol_stats:
                logger.info(
                    f"  {r.protocol_stats.protocol}: "
                    f"TVL=${r.protocol_stats.tvl_usd:,.0f}, "
                    f"{len(r.protocol_stats.pools)} pools"
                )
            for err in r.errors:
                logger.warning(f"  Error: {err}")
    finally:
        await storage.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_main.py -v
```

Expected: PASS

- [ ] **Step 5: Manual integration test — run against real DefiLlama API**

```bash
uv run python -m stake_watch.main
```

Expected: Logs showing TVL and pool data fetched for each enabled protocol. No wallet-specific positions (DefiLlama doesn't provide those).

- [ ] **Step 6: Commit**

```bash
git add src/stake_watch/main.py tests/test_main.py
git commit -m "feat: add main entry point with protocol→collector mapping and single-cycle run"
```

---

### Task 9: APScheduler integration

**Files:**
- Modify: `src/stake_watch/scheduler/runner.py`
- Modify: `src/stake_watch/main.py`
- Test: `tests/scheduler/test_scheduler_integration.py`

- [ ] **Step 1: Write failing test for scheduled execution**

```python
# tests/scheduler/test_scheduler_integration.py
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from stake_watch.scheduler.runner import ScheduledRunner


@pytest.mark.asyncio
async def test_scheduled_runner_registers_jobs():
    mock_collection_runner = AsyncMock()
    scheduled = ScheduledRunner(
        collection_runner=mock_collection_runner,
        position_interval=300,
        stats_interval=900,
    )
    assert scheduled.position_interval == 300
    assert scheduled.stats_interval == 900


@pytest.mark.asyncio
async def test_scheduled_runner_can_trigger_manual():
    mock_collection_runner = AsyncMock()
    mock_collection_runner.run_collection_cycle.return_value = []
    scheduled = ScheduledRunner(
        collection_runner=mock_collection_runner,
        position_interval=300,
        stats_interval=900,
    )
    await scheduled.trigger_now()
    mock_collection_runner.run_collection_cycle.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/scheduler/test_scheduler_integration.py -v
```

Expected: FAIL

- [ ] **Step 3: Add ScheduledRunner to runner.py**

Add to the end of `src/stake_watch/scheduler/runner.py`:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger


class ScheduledRunner:
    def __init__(
        self,
        collection_runner: CollectionRunner,
        position_interval: int = 300,
        stats_interval: int = 900,
    ):
        self.collection_runner = collection_runner
        self.position_interval = position_interval
        self.stats_interval = stats_interval
        self._scheduler = AsyncIOScheduler()

    async def trigger_now(self):
        await self.collection_runner.run_collection_cycle()

    def start(self):
        self._scheduler.add_job(
            self.collection_runner.run_collection_cycle,
            trigger=IntervalTrigger(seconds=self.position_interval),
            id="positions",
            name="Collect positions",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info(
            f"Scheduler started: positions every {self.position_interval}s"
        )

    def stop(self):
        self._scheduler.shutdown(wait=False)
```

Update `src/stake_watch/scheduler/__init__.py`:

```python
from stake_watch.scheduler.runner import CollectionRunner, ScheduledRunner

__all__ = ["CollectionRunner", "ScheduledRunner"]
```

- [ ] **Step 4: Update main.py to use ScheduledRunner**

Replace the `main()` function in `src/stake_watch/main.py`:

```python
async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    runner, storage, settings = await build_app()

    scheduled = ScheduledRunner(
        collection_runner=runner,
        position_interval=settings.intervals.positions,
        stats_interval=settings.intervals.protocol_stats,
    )

    logger.info(
        f"Stake Watch started with {len(runner.collectors)} collectors, "
        f"{len(runner.wallets)} wallets"
    )

    # Run once immediately, then start scheduler
    await scheduled.trigger_now()
    scheduled.start()

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        scheduled.stop()
        await storage.close()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/scheduler/ -v
```

Expected: All 4 tests PASS

- [ ] **Step 6: Run full integration manually**

```bash
uv run python -m stake_watch.main
# Wait 10 seconds, then Ctrl+C
```

Expected: Initial collection runs, scheduler starts, Ctrl+C shuts down cleanly.

- [ ] **Step 7: Commit**

```bash
git add src/stake_watch/scheduler/ src/stake_watch/main.py tests/scheduler/
git commit -m "feat: add APScheduler integration with configurable intervals"
```

---

### Task 10: Run full test suite and verify coverage

- [ ] **Step 1: Run all tests**

```bash
uv run pytest tests/ -v --tb=short
```

Expected: All tests pass (11+ tests)

- [ ] **Step 2: Check coverage**

```bash
uv run pytest tests/ --cov=stake_watch --cov-report=term-missing
```

Expected: >80% coverage on core modules

- [ ] **Step 3: Final commit with any fixes**

```bash
git add -A
git commit -m "chore: P1 foundation complete — config, models, storage, collectors, scheduler"
```

---

## Post-P1 Verification

After completing all tasks, run:

```bash
# Full test suite
uv run pytest tests/ -v

# Manual integration test against real APIs
uv run python -m stake_watch.main

# Verify DB was created and populated
uv run python -c "
import asyncio
from stake_watch.storage.db import Storage
async def check():
    s = Storage('sqlite+aiosqlite:///stake_watch.db')
    await s.initialize()
    # Check if any protocol stats were saved
    stats = await s.get_latest_protocol_stats('aave_v3_base')
    if stats:
        print(f'Aave V3 Base: TVL=\${stats.tvl_usd:,.0f}, {len(stats.pools)} pools')
    else:
        print('No data yet')
    await s.close()
asyncio.run(check())
"
```

Expected: Real DefiLlama data for Aave V3 Base is persisted in SQLite.

---

## Summary

| Task | What it builds | Files created |
|---|---|---|
| 1 | Project skeleton + dependencies | pyproject.toml, .gitignore |
| 2 | Config system (YAML + local overrides) | config.py, settings.yaml, protocols.yaml |
| 3 | Core data models | models/{common,position,protocol}.py |
| 4 | SQLite storage with upsert | storage/{db,tables}.py |
| 5 | BaseCollector ABC | collectors/base.py |
| 6 | DefiLlama collector (first real data) | collectors/defillama.py |
| 7 | CollectionRunner (async batch) | scheduler/runner.py |
| 8 | Main entry point | main.py |
| 9 | APScheduler integration | scheduler/runner.py (modified) |
| 10 | Full test suite verification | — |

---

## Scope Notes

### What P1a delivers
P1a proves the full backend pipeline end-to-end: config (DB-stored) → collector → storage → scheduler. **DefiLlama is the universal first collector** — it provides TVL and yield data for all 10 protocols without needing any RPC keys or chain-specific SDKs. Config is loaded from DB; `config/seed.yaml` populates the DB on first startup.

### What P1b delivers (next plan)
FastAPI config API + React + TypeScript frontend with config management pages (Settings, Protocols, Dashboard). All config CRUD through REST API and web UI.

### What is deferred to P1.5
On-chain protocol-specific collectors (Aave V3 Base, Morpho Base, Jupiter Lend) require chain-specific SDKs, paid RPC endpoints, contract ABIs, and per-wallet position reading.
