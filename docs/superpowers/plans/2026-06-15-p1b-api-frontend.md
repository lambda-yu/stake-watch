# Stake Watch P1b: Config API + React Frontend

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add FastAPI REST API for config management + React + TypeScript frontend SPA so all configuration is managed through the web UI.

**Architecture:** FastAPI serves config CRUD API (`/api/*`) and static React build. React SPA (Vite + Tailwind + shadcn/ui) provides Settings, Protocols, and Dashboard pages. Config stored in SQLite via ConfigStore. FastAPI runs alongside the scheduler in the same process.

**Tech Stack:**
- Backend: FastAPI, uvicorn, pydantic (already installed from P1a)
- Frontend: React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui, React Router
- Testing: pytest + httpx (backend API tests), Vitest (frontend)

**Depends on:** P1a complete (models, storage, collectors, scheduler working)

---

## Chunk 1: Config Store + FastAPI API

### Task 11: ConfigStore — DB config CRUD

**Files:**
- Create: `src/stake_watch/storage/config_store.py`
- Modify: `src/stake_watch/storage/tables.py` — add config tables
- Test: `tests/storage/test_config_store.py`

- [ ] **Step 1: Write failing tests for ConfigStore**

```python
# tests/storage/test_config_store.py
from datetime import datetime, timezone

import pytest

from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage


@pytest.fixture
async def config_store(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    storage = Storage(db_url)
    await storage.initialize()
    store = ConfigStore(storage._session_factory)
    yield store
    await storage.close()


@pytest.mark.asyncio
async def test_wallet_crud(config_store: ConfigStore):
    # Create
    wallet = await config_store.add_wallet("base", "0xTest", "My Wallet")
    assert wallet.chain == "base"
    assert wallet.address == "0xTest"
    assert wallet.id is not None

    # List
    wallets = await config_store.list_wallets()
    assert len(wallets) == 1

    # Delete
    await config_store.delete_wallet(wallet.id)
    wallets = await config_store.list_wallets()
    assert len(wallets) == 0


@pytest.mark.asyncio
async def test_rpc_crud(config_store: ConfigStore):
    await config_store.upsert_rpc("base", "https://mainnet.base.org", [])
    rpc = await config_store.get_rpc("base")
    assert rpc.primary_url == "https://mainnet.base.org"

    await config_store.upsert_rpc("base", "https://new-rpc.base.org", ["https://fallback.base.org"])
    rpc = await config_store.get_rpc("base")
    assert rpc.primary_url == "https://new-rpc.base.org"


@pytest.mark.asyncio
async def test_protocol_crud(config_store: ConfigStore):
    proto = await config_store.add_protocol(
        name="aave_v3_base", chain="base", collector="defillama",
        defillama_slug="aave-v3", safety_score=8.8, enabled=True,
    )
    assert proto.name == "aave_v3_base"

    # Toggle
    await config_store.toggle_protocol(proto.id)
    updated = await config_store.get_protocol(proto.id)
    assert updated.enabled is False

    # List enabled
    all_protos = await config_store.list_protocols()
    assert len(all_protos) == 1


@pytest.mark.asyncio
async def test_app_settings_crud(config_store: ConfigStore):
    await config_store.set_setting("intervals.positions", 300)
    val = await config_store.get_setting("intervals.positions")
    assert val == 300

    await config_store.set_setting("intervals.positions", 60)
    val = await config_store.get_setting("intervals.positions")
    assert val == 60


@pytest.mark.asyncio
async def test_load_full_settings(config_store: ConfigStore):
    await config_store.set_setting("intervals.positions", 300)
    await config_store.set_setting("intervals.protocol_stats", 900)
    await config_store.set_setting("risk.liquidation_warning", 1.3)
    settings = await config_store.load_app_settings()
    assert settings.intervals.positions == 300
    assert settings.risk.liquidation_warning == 1.3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/storage/test_config_store.py -v
```

- [ ] **Step 3: Add config tables to tables.py**

Add to `src/stake_watch/storage/tables.py`:

```python
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
    enabled: Mapped[bool] = mapped_column(default=True)
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
```

- [ ] **Step 4: Implement ConfigStore**

```python
# src/stake_watch/storage/config_store.py
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from stake_watch.config import AppSettings, IntervalConfig, RiskConfig
from stake_watch.storage.tables import (
    AppSettingsRow, ProtocolConfigRow, RpcEndpointRow, WalletRow,
)


class ConfigStore:
    def __init__(self, session_factory: async_sessionmaker):
        self._sf = session_factory

    # --- Wallets ---
    async def add_wallet(self, chain: str, address: str, label: str | None = None) -> WalletRow:
        async with self._sf() as s:
            row = WalletRow(chain=chain, address=address, label=label, created_at=datetime.now(timezone.utc))
            s.add(row)
            await s.commit()
            await s.refresh(row)
            return row

    async def list_wallets(self) -> list[WalletRow]:
        async with self._sf() as s:
            result = await s.execute(select(WalletRow))
            return list(result.scalars().all())

    async def delete_wallet(self, wallet_id: int):
        async with self._sf() as s:
            row = await s.get(WalletRow, wallet_id)
            if row:
                await s.delete(row)
                await s.commit()

    # --- RPC ---
    async def upsert_rpc(self, chain: str, primary_url: str, fallback_urls: list[str]):
        async with self._sf() as s:
            result = await s.execute(select(RpcEndpointRow).where(RpcEndpointRow.chain == chain))
            row = result.scalar_one_or_none()
            now = datetime.now(timezone.utc)
            if row:
                row.primary_url = primary_url
                row.fallback_urls = json.dumps(fallback_urls)
                row.updated_at = now
            else:
                row = RpcEndpointRow(chain=chain, primary_url=primary_url,
                                     fallback_urls=json.dumps(fallback_urls), updated_at=now)
                s.add(row)
            await s.commit()

    async def get_rpc(self, chain: str) -> RpcEndpointRow | None:
        async with self._sf() as s:
            result = await s.execute(select(RpcEndpointRow).where(RpcEndpointRow.chain == chain))
            return result.scalar_one_or_none()

    async def list_rpc(self) -> list[RpcEndpointRow]:
        async with self._sf() as s:
            result = await s.execute(select(RpcEndpointRow))
            return list(result.scalars().all())

    # --- Protocols ---
    async def add_protocol(self, **kwargs) -> ProtocolConfigRow:
        async with self._sf() as s:
            now = datetime.now(timezone.utc)
            row = ProtocolConfigRow(**kwargs, primary_risks=json.dumps(kwargs.pop("primary_risks", [])),
                                    created_at=now, updated_at=now)
            s.add(row)
            await s.commit()
            await s.refresh(row)
            return row

    async def list_protocols(self) -> list[ProtocolConfigRow]:
        async with self._sf() as s:
            result = await s.execute(select(ProtocolConfigRow))
            return list(result.scalars().all())

    async def get_protocol(self, protocol_id: int) -> ProtocolConfigRow | None:
        async with self._sf() as s:
            return await s.get(ProtocolConfigRow, protocol_id)

    async def toggle_protocol(self, protocol_id: int):
        async with self._sf() as s:
            row = await s.get(ProtocolConfigRow, protocol_id)
            if row:
                row.enabled = not row.enabled
                row.updated_at = datetime.now(timezone.utc)
                await s.commit()

    async def delete_protocol(self, protocol_id: int):
        async with self._sf() as s:
            row = await s.get(ProtocolConfigRow, protocol_id)
            if row:
                await s.delete(row)
                await s.commit()

    # --- App Settings ---
    async def set_setting(self, key: str, value):
        async with self._sf() as s:
            result = await s.execute(select(AppSettingsRow).where(AppSettingsRow.key == key))
            row = result.scalar_one_or_none()
            now = datetime.now(timezone.utc)
            if row:
                row.value = json.dumps(value)
                row.updated_at = now
            else:
                row = AppSettingsRow(key=key, value=json.dumps(value), updated_at=now)
                s.add(row)
            await s.commit()

    async def get_setting(self, key: str):
        async with self._sf() as s:
            result = await s.execute(select(AppSettingsRow).where(AppSettingsRow.key == key))
            row = result.scalar_one_or_none()
            return json.loads(row.value) if row else None

    async def load_app_settings(self) -> AppSettings:
        async with self._sf() as s:
            result = await s.execute(select(AppSettingsRow))
            rows = {r.key: json.loads(r.value) for r in result.scalars().all()}

        wallets_rows = await self.list_wallets()
        wallets = [{"chain": w.chain, "address": w.address} for w in wallets_rows]

        return AppSettings(
            wallets=[{"chain": w.chain, "address": w.address} for w in wallets_rows],
            intervals=IntervalConfig(
                positions=rows.get("intervals.positions", 300),
                protocol_stats=rows.get("intervals.protocol_stats", 900),
                stablecoin_price=rows.get("intervals.stablecoin_price", 60),
                stablecoin_supply=rows.get("intervals.stablecoin_supply", 600),
                reserves=rows.get("intervals.reserves", 21600),
            ),
            risk=RiskConfig(
                liquidation_warning=rows.get("risk.liquidation_warning", 1.3),
                liquidation_critical=rows.get("risk.liquidation_critical", 1.1),
                depeg_warning=rows.get("risk.depeg_warning", 0.005),
                depeg_critical=rows.get("risk.depeg_critical", 0.02),
                tvl_crash_threshold=rows.get("risk.tvl_crash_threshold", 0.15),
                apy_change_threshold=rows.get("risk.apy_change_threshold", 0.30),
            ),
        )
```

- [ ] **Step 5: Run tests, verify pass**

```bash
uv run pytest tests/storage/test_config_store.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/stake_watch/storage/ tests/storage/
git commit -m "feat: add ConfigStore for DB-backed config management"
```

---

### Task 12: FastAPI application + config API routes

**Files:**
- Create: `src/stake_watch/api/__init__.py`
- Create: `src/stake_watch/api/app.py`
- Create: `src/stake_watch/api/deps.py`
- Create: `src/stake_watch/api/routes/config.py`
- Create: `src/stake_watch/api/routes/protocols.py`
- Create: `src/stake_watch/api/routes/status.py`
- Test: `tests/api/test_config_routes.py`
- Test: `tests/api/test_protocol_routes.py`

- [ ] **Step 1: Add FastAPI + uvicorn dependencies**

```bash
uv add fastapi uvicorn[standard]
```

- [ ] **Step 2: Write failing tests for config API**

```python
# tests/api/__init__.py
# (empty)
```

```python
# tests/api/test_config_routes.py
import pytest
from httpx import ASGITransport, AsyncClient

from stake_watch.api.app import create_app
from stake_watch.storage.db import Storage


@pytest.fixture
async def client(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    storage = Storage(db_url)
    await storage.initialize()
    app = create_app(storage)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await storage.close()


@pytest.mark.asyncio
async def test_list_wallets_empty(client):
    resp = await client.get("/api/config/wallets")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_add_and_list_wallet(client):
    resp = await client.post("/api/config/wallets", json={
        "chain": "base", "address": "0xTest", "label": "Test Wallet"
    })
    assert resp.status_code == 201
    wallet = resp.json()
    assert wallet["chain"] == "base"
    assert wallet["id"] is not None

    resp = await client.get("/api/config/wallets")
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_delete_wallet(client):
    resp = await client.post("/api/config/wallets", json={
        "chain": "base", "address": "0xTest"
    })
    wallet_id = resp.json()["id"]

    resp = await client.delete(f"/api/config/wallets/{wallet_id}")
    assert resp.status_code == 204

    resp = await client.get("/api/config/wallets")
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_update_intervals(client):
    resp = await client.put("/api/config/intervals", json={
        "positions": 60, "protocol_stats": 300
    })
    assert resp.status_code == 200

    resp = await client.get("/api/config/intervals")
    data = resp.json()
    assert data["positions"] == 60
    assert data["protocol_stats"] == 300
```

```python
# tests/api/test_protocol_routes.py
import pytest
from httpx import ASGITransport, AsyncClient

from stake_watch.api.app import create_app
from stake_watch.storage.db import Storage


@pytest.fixture
async def client(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    storage = Storage(db_url)
    await storage.initialize()
    app = create_app(storage)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await storage.close()


@pytest.mark.asyncio
async def test_add_and_list_protocols(client):
    resp = await client.post("/api/protocols", json={
        "name": "aave_v3_base", "chain": "base", "collector": "defillama",
        "defillama_slug": "aave-v3", "safety_score": 8.8, "enabled": True,
    })
    assert resp.status_code == 201

    resp = await client.get("/api/protocols")
    protos = resp.json()
    assert len(protos) == 1
    assert protos[0]["name"] == "aave_v3_base"


@pytest.mark.asyncio
async def test_toggle_protocol(client):
    resp = await client.post("/api/protocols", json={
        "name": "test", "chain": "base", "collector": "defillama", "enabled": True,
    })
    proto_id = resp.json()["id"]

    resp = await client.patch(f"/api/protocols/{proto_id}/toggle")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
```

- [ ] **Step 3: Implement FastAPI app + routes**

Create `src/stake_watch/api/__init__.py` (empty), then:

```python
# src/stake_watch/api/deps.py
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage

_storage: Storage | None = None
_config_store: ConfigStore | None = None


def init_deps(storage: Storage):
    global _storage, _config_store
    _storage = storage
    _config_store = ConfigStore(storage._session_factory)


def get_config_store() -> ConfigStore:
    assert _config_store is not None
    return _config_store


def get_storage() -> Storage:
    assert _storage is not None
    return _storage
```

```python
# src/stake_watch/api/app.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from stake_watch.api import deps
from stake_watch.api.routes import config, protocols, status
from stake_watch.storage.db import Storage


def create_app(storage: Storage) -> FastAPI:
    app = FastAPI(title="Stake Watch", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    deps.init_deps(storage)
    app.include_router(config.router, prefix="/api/config", tags=["config"])
    app.include_router(protocols.router, prefix="/api/protocols", tags=["protocols"])
    app.include_router(status.router, prefix="/api/status", tags=["status"])
    return app
```

```python
# src/stake_watch/api/routes/__init__.py
# (empty)
```

```python
# src/stake_watch/api/routes/config.py
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from stake_watch.api.deps import get_config_store
from stake_watch.storage.config_store import ConfigStore

router = APIRouter()


class WalletCreate(BaseModel):
    chain: str
    address: str
    label: str | None = None


class WalletResponse(BaseModel):
    id: int
    chain: str
    address: str
    label: str | None


class IntervalsUpdate(BaseModel):
    positions: int | None = None
    protocol_stats: int | None = None
    stablecoin_price: int | None = None
    stablecoin_supply: int | None = None
    reserves: int | None = None


@router.get("/wallets")
async def list_wallets(store: ConfigStore = Depends(get_config_store)):
    wallets = await store.list_wallets()
    return [WalletResponse(id=w.id, chain=w.chain, address=w.address, label=w.label) for w in wallets]


@router.post("/wallets", status_code=201)
async def add_wallet(data: WalletCreate, store: ConfigStore = Depends(get_config_store)):
    w = await store.add_wallet(data.chain, data.address, data.label)
    return WalletResponse(id=w.id, chain=w.chain, address=w.address, label=w.label)


@router.delete("/wallets/{wallet_id}", status_code=204)
async def delete_wallet(wallet_id: int, store: ConfigStore = Depends(get_config_store)):
    await store.delete_wallet(wallet_id)
    return Response(status_code=204)


@router.get("/intervals")
async def get_intervals(store: ConfigStore = Depends(get_config_store)):
    settings = await store.load_app_settings()
    return settings.intervals.model_dump()


@router.put("/intervals")
async def update_intervals(data: IntervalsUpdate, store: ConfigStore = Depends(get_config_store)):
    for field, value in data.model_dump(exclude_none=True).items():
        await store.set_setting(f"intervals.{field}", value)
    settings = await store.load_app_settings()
    return settings.intervals.model_dump()


@router.get("/risk")
async def get_risk(store: ConfigStore = Depends(get_config_store)):
    settings = await store.load_app_settings()
    return settings.risk.model_dump()


@router.put("/risk")
async def update_risk(data: dict, store: ConfigStore = Depends(get_config_store)):
    for key, value in data.items():
        await store.set_setting(f"risk.{key}", value)
    settings = await store.load_app_settings()
    return settings.risk.model_dump()
```

```python
# src/stake_watch/api/routes/protocols.py
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from stake_watch.api.deps import get_config_store
from stake_watch.storage.config_store import ConfigStore

router = APIRouter()


class ProtocolCreate(BaseModel):
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


@router.get("")
async def list_protocols(store: ConfigStore = Depends(get_config_store)):
    protos = await store.list_protocols()
    return [_to_dict(p) for p in protos]


@router.post("", status_code=201)
async def add_protocol(data: ProtocolCreate, store: ConfigStore = Depends(get_config_store)):
    p = await store.add_protocol(**data.model_dump())
    return _to_dict(p)


@router.patch("/{protocol_id}/toggle")
async def toggle_protocol(protocol_id: int, store: ConfigStore = Depends(get_config_store)):
    await store.toggle_protocol(protocol_id)
    p = await store.get_protocol(protocol_id)
    return _to_dict(p)


@router.delete("/{protocol_id}", status_code=204)
async def delete_protocol(protocol_id: int, store: ConfigStore = Depends(get_config_store)):
    await store.delete_protocol(protocol_id)
    return Response(status_code=204)


def _to_dict(p):
    import json
    return {
        "id": p.id, "name": p.name, "chain": p.chain,
        "collector": p.collector, "enabled": p.enabled,
        "safety_rank": p.safety_rank, "safety_score": p.safety_score,
        "reference_apy": p.reference_apy,
        "primary_risks": json.loads(p.primary_risks) if p.primary_risks else [],
        "vault_address": p.vault_address,
        "defillama_slug": p.defillama_slug,
    }
```

```python
# src/stake_watch/api/routes/status.py
from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def system_status():
    return {"status": "running", "version": "0.1.0"}
```

- [ ] **Step 4: Run tests, verify pass**

```bash
uv run pytest tests/api/ -v
```

- [ ] **Step 5: Commit**

```bash
git add src/stake_watch/api/ tests/api/
git commit -m "feat: add FastAPI config API with wallet, protocol, intervals, risk CRUD"
```

---

## Chunk 2: React Frontend

### Task 13: Initialize React frontend

**Files:**
- Create: `frontend/` directory (Vite + React + TypeScript + Tailwind)

- [ ] **Step 1: Create Vite React project**

```bash
cd /Users/user/yu/code/stake-watch
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install -D tailwindcss @tailwindcss/vite
npm install react-router-dom
```

- [ ] **Step 2: Configure Tailwind**

Update `frontend/vite.config.ts`:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
```

Update `frontend/src/index.css`:

```css
@import "tailwindcss";
```

- [ ] **Step 3: Create API client**

```typescript
// frontend/src/api/client.ts
const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (resp.status === 204) return undefined as T;
  if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
  return resp.json();
}

export const api = {
  wallets: {
    list: () => request<any[]>('/config/wallets'),
    add: (data: { chain: string; address: string; label?: string }) =>
      request<any>('/config/wallets', { method: 'POST', body: JSON.stringify(data) }),
    delete: (id: number) =>
      request<void>(`/config/wallets/${id}`, { method: 'DELETE' }),
  },
  protocols: {
    list: () => request<any[]>('/protocols'),
    add: (data: any) =>
      request<any>('/protocols', { method: 'POST', body: JSON.stringify(data) }),
    toggle: (id: number) =>
      request<any>(`/protocols/${id}/toggle`, { method: 'PATCH' }),
    delete: (id: number) =>
      request<void>(`/protocols/${id}`, { method: 'DELETE' }),
  },
  intervals: {
    get: () => request<any>('/config/intervals'),
    update: (data: any) =>
      request<any>('/config/intervals', { method: 'PUT', body: JSON.stringify(data) }),
  },
  risk: {
    get: () => request<any>('/config/risk'),
    update: (data: any) =>
      request<any>('/config/risk', { method: 'PUT', body: JSON.stringify(data) }),
  },
  status: {
    get: () => request<any>('/status'),
  },
};
```

- [ ] **Step 4: Create Layout + Router**

```tsx
// frontend/src/App.tsx
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { Dashboard } from './pages/Dashboard';
import { Settings } from './pages/Settings';
import { Protocols } from './pages/Protocols';

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <nav className="border-b border-gray-800 px-6 py-3 flex gap-6 items-center">
        <span className="text-lg font-bold text-white">Stake Watch</span>
        <NavLink to="/" className={({ isActive }) =>
          isActive ? 'text-blue-400' : 'text-gray-400 hover:text-gray-200'
        }>Dashboard</NavLink>
        <NavLink to="/settings" className={({ isActive }) =>
          isActive ? 'text-blue-400' : 'text-gray-400 hover:text-gray-200'
        }>Settings</NavLink>
        <NavLink to="/protocols" className={({ isActive }) =>
          isActive ? 'text-blue-400' : 'text-gray-400 hover:text-gray-200'
        }>Protocols</NavLink>
      </nav>
      <main className="p-6">{children}</main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/protocols" element={<Protocols />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
```

- [ ] **Step 5: Create placeholder pages**

```tsx
// frontend/src/pages/Dashboard.tsx
import { useEffect, useState } from 'react';
import { api } from '../api/client';

export function Dashboard() {
  const [status, setStatus] = useState<any>(null);
  useEffect(() => { api.status.get().then(setStatus); }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Dashboard</h1>
      <pre className="bg-gray-900 p-4 rounded text-sm">
        {JSON.stringify(status, null, 2)}
      </pre>
    </div>
  );
}
```

```tsx
// frontend/src/pages/Settings.tsx
export function Settings() {
  return <div><h1 className="text-2xl font-bold mb-4">Settings</h1><p>Coming in Task 14</p></div>;
}
```

```tsx
// frontend/src/pages/Protocols.tsx
export function Protocols() {
  return <div><h1 className="text-2xl font-bold mb-4">Protocols</h1><p>Coming in Task 15</p></div>;
}
```

- [ ] **Step 6: Verify frontend builds and dev server works**

```bash
cd /Users/user/yu/code/stake-watch/frontend
npm run dev
# Open http://localhost:5173, verify layout renders
```

- [ ] **Step 7: Commit**

```bash
cd /Users/user/yu/code/stake-watch
git add frontend/
git commit -m "feat: initialize React frontend with Vite + Tailwind + router + API client"
```

---

### Task 14: Settings management page

**Files:**
- Modify: `frontend/src/pages/Settings.tsx`
- Create: `frontend/src/components/WalletForm.tsx`
- Create: `frontend/src/components/ThresholdEditor.tsx`

- [ ] **Step 1: Implement WalletForm component**

```tsx
// frontend/src/components/WalletForm.tsx
import { useState } from 'react';

type Props = {
  onAdd: (wallet: { chain: string; address: string; label?: string }) => void;
};

const CHAINS = ['base', 'ethereum', 'solana', 'bsc'];

export function WalletForm({ onAdd }: Props) {
  const [chain, setChain] = useState('base');
  const [address, setAddress] = useState('');
  const [label, setLabel] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!address.trim()) return;
    onAdd({ chain, address: address.trim(), label: label.trim() || undefined });
    setAddress('');
    setLabel('');
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-2 items-end">
      <select value={chain} onChange={e => setChain(e.target.value)}
        className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm">
        {CHAINS.map(c => <option key={c} value={c}>{c}</option>)}
      </select>
      <input value={address} onChange={e => setAddress(e.target.value)}
        placeholder="Wallet address" className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm flex-1" />
      <input value={label} onChange={e => setLabel(e.target.value)}
        placeholder="Label (optional)" className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm w-40" />
      <button type="submit" className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded text-sm">Add</button>
    </form>
  );
}
```

- [ ] **Step 2: Implement full Settings page**

```tsx
// frontend/src/pages/Settings.tsx
import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { WalletForm } from '../components/WalletForm';

export function Settings() {
  const [wallets, setWallets] = useState<any[]>([]);
  const [intervals, setIntervals] = useState<any>({});
  const [risk, setRisk] = useState<any>({});

  const reload = async () => {
    setWallets(await api.wallets.list());
    setIntervals(await api.intervals.get());
    setRisk(await api.risk.get());
  };
  useEffect(() => { reload(); }, []);

  const addWallet = async (data: any) => {
    await api.wallets.add(data);
    reload();
  };
  const deleteWallet = async (id: number) => {
    await api.wallets.delete(id);
    reload();
  };
  const updateInterval = async (key: string, value: number) => {
    await api.intervals.update({ [key]: value });
    reload();
  };
  const updateRisk = async (key: string, value: number) => {
    await api.risk.update({ [key]: value });
    reload();
  };

  return (
    <div className="space-y-8 max-w-4xl">
      <section>
        <h2 className="text-xl font-semibold mb-3">Wallets</h2>
        <WalletForm onAdd={addWallet} />
        <div className="mt-3 space-y-2">
          {wallets.map(w => (
            <div key={w.id} className="flex items-center justify-between bg-gray-900 rounded p-3">
              <div>
                <span className="text-xs bg-gray-700 px-2 py-0.5 rounded mr-2">{w.chain}</span>
                <span className="font-mono text-sm">{w.address}</span>
                {w.label && <span className="text-gray-500 ml-2 text-sm">{w.label}</span>}
              </div>
              <button onClick={() => deleteWallet(w.id)} className="text-red-400 hover:text-red-300 text-sm">Remove</button>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-xl font-semibold mb-3">Polling Intervals (seconds)</h2>
        <div className="grid grid-cols-2 gap-3">
          {Object.entries(intervals).map(([key, val]) => (
            <div key={key} className="flex items-center gap-2">
              <label className="text-sm text-gray-400 w-40">{key}</label>
              <input type="number" value={val as number} onChange={e => updateInterval(key, Number(e.target.value))}
                className="bg-gray-800 border border-gray-700 rounded px-3 py-1 text-sm w-24" />
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-xl font-semibold mb-3">Risk Thresholds</h2>
        <div className="grid grid-cols-2 gap-3">
          {Object.entries(risk).map(([key, val]) => (
            <div key={key} className="flex items-center gap-2">
              <label className="text-sm text-gray-400 w-48">{key}</label>
              <input type="number" step="0.01" value={val as number} onChange={e => updateRisk(key, Number(e.target.value))}
                className="bg-gray-800 border border-gray-700 rounded px-3 py-1 text-sm w-24" />
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 3: Test in browser**

```bash
# Terminal 1: Backend
cd /Users/user/yu/code/stake-watch
uv run python -m stake_watch.main

# Terminal 2: Frontend
cd /Users/user/yu/code/stake-watch/frontend
npm run dev
```

Open http://localhost:5173/settings. Verify:
- Can add a wallet → appears in list
- Can delete a wallet → removed
- Can change interval → persists on refresh
- Can change risk threshold → persists on refresh

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "feat: add Settings page with wallet, interval, risk management"
```

---

### Task 15: Protocols management page

**Files:**
- Modify: `frontend/src/pages/Protocols.tsx`
- Create: `frontend/src/components/ProtocolCard.tsx`

- [ ] **Step 1: Implement ProtocolCard**

```tsx
// frontend/src/components/ProtocolCard.tsx
type Protocol = {
  id: number; name: string; chain: string; collector: string;
  enabled: boolean; safety_score: number | null; reference_apy: string | null;
  primary_risks: string[];
};

type Props = {
  protocol: Protocol;
  onToggle: (id: number) => void;
  onDelete: (id: number) => void;
};

export function ProtocolCard({ protocol: p, onToggle, onDelete }: Props) {
  return (
    <div className={`bg-gray-900 rounded-lg p-4 border ${p.enabled ? 'border-gray-700' : 'border-gray-800 opacity-60'}`}>
      <div className="flex justify-between items-start">
        <div>
          <h3 className="font-semibold">{p.name}</h3>
          <div className="flex gap-2 mt-1">
            <span className="text-xs bg-gray-700 px-2 py-0.5 rounded">{p.chain}</span>
            {p.safety_score && <span className="text-xs bg-green-900 text-green-300 px-2 py-0.5 rounded">{p.safety_score}/10</span>}
            {p.reference_apy && <span className="text-xs bg-blue-900 text-blue-300 px-2 py-0.5 rounded">{p.reference_apy}</span>}
          </div>
          {p.primary_risks.length > 0 && (
            <div className="mt-2 text-xs text-gray-500">{p.primary_risks.join(' / ')}</div>
          )}
        </div>
        <div className="flex gap-2">
          <button onClick={() => onToggle(p.id)}
            className={`text-xs px-3 py-1 rounded ${p.enabled ? 'bg-green-800 text-green-200' : 'bg-gray-700 text-gray-400'}`}>
            {p.enabled ? 'Enabled' : 'Disabled'}
          </button>
          <button onClick={() => onDelete(p.id)} className="text-xs text-red-400 hover:text-red-300">Delete</button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Implement Protocols page with add form**

```tsx
// frontend/src/pages/Protocols.tsx
import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { ProtocolCard } from '../components/ProtocolCard';

const CHAINS = ['base', 'ethereum', 'solana', 'bsc'];

export function Protocols() {
  const [protocols, setProtocols] = useState<any[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', chain: 'base', collector: 'defillama', defillama_slug: '', safety_score: '' });

  const reload = async () => setProtocols(await api.protocols.list());
  useEffect(() => { reload(); }, []);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    await api.protocols.add({
      ...form,
      safety_score: form.safety_score ? Number(form.safety_score) : null,
      enabled: true,
    });
    setForm({ name: '', chain: 'base', collector: 'defillama', defillama_slug: '', safety_score: '' });
    setShowForm(false);
    reload();
  };

  return (
    <div className="max-w-4xl">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-bold">Protocols</h1>
        <button onClick={() => setShowForm(!showForm)}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded text-sm">
          {showForm ? 'Cancel' : 'Add Protocol'}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleAdd} className="bg-gray-900 rounded-lg p-4 mb-4 grid grid-cols-2 gap-3">
          <input value={form.name} onChange={e => setForm({...form, name: e.target.value})}
            placeholder="Protocol name" className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
          <select value={form.chain} onChange={e => setForm({...form, chain: e.target.value})}
            className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm">
            {CHAINS.map(c => <option key={c}>{c}</option>)}
          </select>
          <input value={form.defillama_slug} onChange={e => setForm({...form, defillama_slug: e.target.value})}
            placeholder="DefiLlama slug" className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
          <input value={form.safety_score} onChange={e => setForm({...form, safety_score: e.target.value})}
            placeholder="Safety score (0-10)" type="number" step="0.1"
            className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
          <button type="submit" className="col-span-2 bg-green-600 hover:bg-green-700 text-white py-2 rounded text-sm">Save</button>
        </form>
      )}

      <div className="space-y-3">
        {protocols.map(p => (
          <ProtocolCard key={p.id} protocol={p}
            onToggle={async (id) => { await api.protocols.toggle(id); reload(); }}
            onDelete={async (id) => { await api.protocols.delete(id); reload(); }}
          />
        ))}
        {protocols.length === 0 && <p className="text-gray-500">No protocols configured. Add one above.</p>}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Test in browser**

Verify:
- Protocol list shows all configured protocols
- Can add a new protocol via form
- Can toggle enable/disable → visual state changes
- Can delete a protocol
- Data persists on page refresh

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "feat: add Protocols management page with add/toggle/delete"
```

---

### Task 16: Update main.py to serve FastAPI + scheduler together

**Files:**
- Modify: `src/stake_watch/main.py`

- [ ] **Step 1: Update main.py**

```python
# Replace main() in src/stake_watch/main.py
import uvicorn
from stake_watch.api.app import create_app

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    runner, storage, settings = await build_app()

    # Create FastAPI app
    app = create_app(storage)

    # Setup scheduler
    scheduled = ScheduledRunner(
        collection_runner=runner,
        position_interval=settings.intervals.positions,
        stats_interval=settings.intervals.protocol_stats,
    )

    logger.info(
        f"Stake Watch started with {len(runner.collectors)} collectors, "
        f"{len(runner.wallets)} wallets"
    )

    # Run initial collection + start scheduler
    await scheduled.trigger_now()
    scheduled.start()

    # Run FastAPI server
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    try:
        await server.serve()
    finally:
        scheduled.stop()
        await storage.close()
```

- [ ] **Step 2: Test end-to-end**

```bash
uv run python -m stake_watch.main
# Opens on http://localhost:8000
# Frontend dev: cd frontend && npm run dev → http://localhost:5173
```

Verify: Backend API works, frontend connects via proxy, config changes persist.

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest tests/ -v
```

- [ ] **Step 4: Commit**

```bash
git add src/stake_watch/main.py
git commit -m "feat: serve FastAPI + scheduler together in main entry point"
```

---

## Summary

| Task | What it builds | Files |
|---|---|---|
| 11 | ConfigStore — DB config CRUD | storage/config_store.py, tables.py |
| 12 | FastAPI config API routes | api/app.py, routes/{config,protocols,status}.py |
| 13 | React frontend skeleton | frontend/ (Vite + Tailwind + Router + API client) |
| 14 | Settings page (wallets, intervals, thresholds) | pages/Settings.tsx, components/WalletForm.tsx |
| 15 | Protocols page (list, add, toggle, delete) | pages/Protocols.tsx, components/ProtocolCard.tsx |
| 16 | Main entry serves FastAPI + scheduler | main.py |
