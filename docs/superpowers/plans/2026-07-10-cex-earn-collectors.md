# CEX Earn Collectors Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add USDT/USDC flexible-earn APY collection from Binance, OKX, Bybit, Gate, and Bitget as a parallel subsystem alongside the existing DeFi monitoring, surfaced in a new `/cex` React tab.

**Architecture:** Follow the split-across-standard-folders convention already used for stablecoin code. Collectors live under `src/stake_watch/collectors/cex/` (one file per venue) behind a `CexEarnCollector` ABC; two new ORM rows (`CexEarnRateRow` append-only, `CexVenueRow` mutable) join `storage/tables.py`; a new `_refresh_cex_rates` job on `ScheduledRunner` polls all enabled venues concurrently on its own interval; a new `api/routes/cex.py` router exposes `/api/cex/*`; a new `frontend/src/pages/Cex.tsx` page renders a sortable rate table with venue-management controls.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async + aiosqlite, APScheduler, httpx, pytest + pytest-asyncio, React 18 + TypeScript + Tailwind, Vite.

**Reference spec:** `docs/superpowers/specs/2026-07-10-cex-earn-collectors-design.md`

**Follow throughout:**
- @superpowers:test-driven-development — every task writes the failing test first
- @superpowers:verification-before-completion — before marking a chunk done, run the tests and paste the actual output
- Conventional commits (`feat(cex): …`, `test(cex): …`, `docs(cex): …`) with the Claude co-author trailer — see `docs/git/commits.md`
- Work directly on branch `feature/cex-earn-collectors` (spec was already committed there); do not merge to main until the whole plan is green

---

## Chunk 1: Endpoint spike

**Purpose:** Verify each of the five CEX public endpoints before we build the collectors around them. Capture real response fragments as test fixtures. The spec explicitly flags Binance / Bybit / Gate as risky — if any prove auth-only or Cloudflare-walled, note the fallback strategy here and disable that venue in seed for now.

**Files:**
- Create: `scripts/cex_spike.py` (throwaway probe script; deleted at the end of the chunk)
- Create: `tests/cex/__init__.py`
- Create: `tests/cex/fixtures/binance_earn.json`
- Create: `tests/cex/fixtures/okx_earn.json`
- Create: `tests/cex/fixtures/bybit_earn.json`
- Create: `tests/cex/fixtures/gate_earn.json`
- Create: `tests/cex/fixtures/bitget_earn.json`
- Create: `docs/superpowers/specs/2026-07-10-cex-earn-collectors-design.md` (append **Endpoint verification results** section — do not rewrite the spec, only append)

**Follow @superpowers:systematic-debugging if any venue misbehaves — the failure mode dictates the fallback strategy.**

- [ ] **Step 1: Scaffold the spike script**

Create `scripts/cex_spike.py`:

```python
"""One-shot probe: hit each CEX Earn endpoint, dump the response.
Run once, capture fixtures, then delete this file. Not shipped.
"""
import asyncio, json, sys
from pathlib import Path
import httpx

OUT = Path("tests/cex/fixtures"); OUT.mkdir(parents=True, exist_ok=True)

async def probe(name: str, method: str, url: str, **kw) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
            r = await c.request(method, url, **kw)
        print(f"{name}: {r.status_code} {url}")
        if r.status_code != 200:
            print(f"  body[:200]={r.text[:200]!r}")
            return None
        data = r.json()
        (OUT / f"{name}_earn.json").write_text(json.dumps(data, indent=2)[:200_000])
        return data
    except Exception as e:
        print(f"{name}: EXC {e!r}")
        return None

async def main():
    await probe("binance", "POST",
        "https://www.binance.com/bapi/earn/v2/friendly/finance-earn/simple/all",
        json={"pageSize": 200, "pageIndex": 1, "asset": None, "status": "ALL"},
        headers={"Content-Type": "application/json", "clientType": "web"})
    await probe("okx_usdt", "GET",
        "https://www.okx.com/api/v5/finance/savings/lending-rate-summary?ccy=USDT")
    await probe("okx_usdc", "GET",
        "https://www.okx.com/api/v5/finance/savings/lending-rate-summary?ccy=USDC")
    await probe("bybit", "GET",
        "https://api.bybit.com/v5/earn/product?category=FlexibleSaving&coin=USDT")
    # Gate.io correct host is api.gateio.ws (not gateapi.io)
    await probe("gate", "GET",
        "https://api.gateio.ws/api/v4/earn/uni/currencies/USDT")
    await probe("bitget", "GET",
        "https://api.bitget.com/api/v2/earn/savings/product?filter=available_and_held&coin=USDT")

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run the spike**

```bash
uv run python scripts/cex_spike.py
```

Expected: five OK lines and five files under `tests/cex/fixtures/`. Any 403 / 451 / captcha / auth-error is a fallback signal — note it and move on. **Do not block on a single failing venue.**

- [ ] **Step 3: Merge OKX USDT+USDC fixtures**

Combine `okx_usdt_earn.json` + `okx_usdc_earn.json` into a single `okx_earn.json` shaped as `{"USDT": <resp>, "USDC": <resp>}` (the collector will call the URL twice at runtime; the fixture just needs to expose both bodies for tests). Delete the two intermediate files.

- [ ] **Step 4: Append verification section to the spec**

Add at the end of `docs/superpowers/specs/2026-07-10-cex-earn-collectors-design.md`:

```markdown
## Appendix: Endpoint verification (spike results, YYYY-MM-DD)

| Venue   | Status                             | URL used                                             | Response shape summary                                     |
|---------|------------------------------------|------------------------------------------------------|------------------------------------------------------------|
| Binance | OK / needs-scraping / disabled     | (final URL, headers)                                 | (top-level keys; where FLEXIBLE rows live; tier array key) |
| OKX     | OK                                 | …                                                    | …                                                          |
| Bybit   | …                                  | …                                                    | …                                                          |
| Gate    | …                                  | …                                                    | …                                                          |
| Bitget  | …                                  | …                                                    | …                                                          |

**Ship order for per-venue collectors (Chunk 5):** OKX first (most reliable),
then the rest in verified-working order; any venue marked "disabled" ships
with `enabled=false` in seed and a follow-up TODO in `notes`.
```

- [ ] **Step 5: Delete the spike script**

```bash
rm scripts/cex_spike.py
```

- [ ] **Step 6: Commit**

```bash
git add tests/cex/ docs/superpowers/specs/2026-07-10-cex-earn-collectors-design.md
git commit -m "test(cex): capture Earn endpoint fixtures + verification notes

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**Chunk 1 done when:** `tests/cex/fixtures/*.json` exists for at least OKX and Bitget (worst case), the spec appendix documents every venue's status, and the spike script is deleted.

---

## Chunk 2: Data models + ORM tables + storage methods

**Purpose:** Add the Pydantic models, ORM rows, and CRUD methods that everything else depends on. Pure data plumbing — no HTTP, no scheduler, no HTTP handlers.

**Files:**
- Create: `src/stake_watch/models/cex.py`
- Modify: `src/stake_watch/storage/tables.py` (append two `Base` subclasses)
- Modify: `src/stake_watch/storage/db.py` (add three methods to `Storage`)
- Create: `tests/storage/test_cex_rates.py`

- [ ] **Step 1: Write failing tests for models**

Create `tests/models/test_cex_models.py`:

```python
from datetime import datetime, timezone
from stake_watch.models.cex import CexEarnRate, VenueRateSnapshot, CexVenue

def test_cex_earn_rate_defaults_product_type_and_max_equals_min():
    now = datetime.now(timezone.utc)
    r = CexEarnRate(venue="okx", asset="USDT", apy_min=0.04, apy_max=0.04, updated_at=now)
    assert r.product_type == "flexible"
    assert r.tier_note is None and r.raw_json is None

def test_cex_venue_defaults():
    v = CexVenue(name="binance", display_name="Binance")
    assert v.enabled is True and v.assets == ["USDT", "USDC"]

def test_snapshot_default_errors_empty():
    s = VenueRateSnapshot(venue="okx", rates=[])
    assert s.errors == []
```

- [ ] **Step 2: Run — verify fails with import error**

```bash
uv run pytest tests/models/test_cex_models.py -v
```
Expected: ModuleNotFoundError for `stake_watch.models.cex`.

- [ ] **Step 3: Implement `src/stake_watch/models/cex.py`**

```python
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel

class CexEarnRate(BaseModel):
    venue: str
    asset: str
    product_type: str = "flexible"
    apy_min: float
    apy_max: float
    tier_note: str | None = None
    raw_json: str | None = None
    updated_at: datetime

class VenueRateSnapshot(BaseModel):
    venue: str
    rates: list[CexEarnRate] = []
    errors: list[str] = []

class CexVenue(BaseModel):
    name: str
    display_name: str
    enabled: bool = True
    assets: list[str] = ["USDT", "USDC"]
    notes: str | None = None
```

- [ ] **Step 4: Run — verify model tests pass**

```bash
uv run pytest tests/models/test_cex_models.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Add ORM rows to `storage/tables.py`**

Append (after the last existing row class, before any `Index(...)` module-level statements — inspect the file first to find the right spot):

```python
class CexEarnRateRow(Base):
    __tablename__ = "cex_earn_rates"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    venue: Mapped[str] = mapped_column(String(30))
    asset: Mapped[str] = mapped_column(String(20))
    product_type: Mapped[str] = mapped_column(String(30), default="flexible")
    apy_min: Mapped[float] = mapped_column(Float)
    apy_max: Mapped[float] = mapped_column(Float)
    tier_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("ix_cex_rates_lookup", "venue", "asset", "product_type", "updated_at"),
    )

class CexVenueRow(Base):
    __tablename__ = "cex_venues"
    name: Mapped[str] = mapped_column(String(30), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(50))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    assets_json: Mapped[str] = mapped_column(Text, default='["USDT","USDC"]')
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

Ensure the imports at the top of `tables.py` include `Boolean`, `Float`, `Text`, `Index`, `String`, `DateTime` (add whichever are missing).

- [ ] **Step 6: Write failing tests for Storage methods**

Create `tests/storage/test_cex_rates.py`:

```python
import pytest
from datetime import datetime, timezone, timedelta
from stake_watch.storage.db import Storage
from stake_watch.models.cex import CexEarnRate

@pytest.fixture
async def storage():
    s = Storage("sqlite+aiosqlite:///:memory:")
    await s.initialize()
    yield s
    await s.close()

def _rate(venue, asset, apy_min, apy_max, updated_at):
    return CexEarnRate(venue=venue, asset=asset, apy_min=apy_min,
                       apy_max=apy_max, updated_at=updated_at)

@pytest.mark.asyncio
async def test_insert_and_latest(storage):
    now = datetime.now(timezone.utc)
    older = now - timedelta(minutes=30)
    await storage.insert_cex_rates([
        _rate("okx", "USDT", 0.03, 0.03, older),
        _rate("okx", "USDT", 0.04, 0.05, now),
    ])
    rows = await storage.list_latest_cex_rates()
    assert len(rows) == 1
    assert rows[0].apy_min == 0.04 and rows[0].apy_max == 0.05

@pytest.mark.asyncio
async def test_history_filter(storage):
    now = datetime.now(timezone.utc)
    await storage.insert_cex_rates([
        _rate("okx", "USDT", 0.03, 0.03, now - timedelta(hours=2)),
        _rate("okx", "USDT", 0.04, 0.04, now - timedelta(hours=1)),
        _rate("okx", "USDT", 0.05, 0.05, now),
        _rate("binance", "USDT", 0.06, 0.06, now),
    ])
    rows = await storage.list_cex_history(venue="okx", asset="USDT",
        since=now - timedelta(hours=90/60), limit=10)
    # since = now - 1.5h, so first entry (2h ago) is excluded
    assert len(rows) == 2
    assert all(r.venue == "okx" for r in rows)
```

- [ ] **Step 7: Run — verify fails**

```bash
uv run pytest tests/storage/test_cex_rates.py -v
```
Expected: AttributeError on `insert_cex_rates`.

- [ ] **Step 8: Implement Storage methods**

Add to `src/stake_watch/storage/db.py` (imports for the new row + `CexEarnRate` model at the top; methods appended at the bottom of the `Storage` class):

```python
# top of file — extend imports
from stake_watch.storage.tables import CexEarnRateRow  # noqa
from stake_watch.models.cex import CexEarnRate  # noqa

# inside class Storage:
async def insert_cex_rates(self, rates: list[CexEarnRate]) -> None:
    if not rates:
        return
    async with self._session_factory() as session:
        for r in rates:
            session.add(CexEarnRateRow(
                venue=r.venue, asset=r.asset, product_type=r.product_type,
                apy_min=r.apy_min, apy_max=r.apy_max,
                tier_note=r.tier_note, raw_json=r.raw_json,
                updated_at=r.updated_at,
            ))
        await session.commit()

async def list_latest_cex_rates(self) -> list[CexEarnRateRow]:
    """Return one row per (venue, asset, product_type), the most recent."""
    async with self._session_factory() as session:
        # Grouped max: fetch all rows sorted, then dedupe on the key in Python.
        # SQLite window-function alternative is overkill for O(venues*assets) rows.
        result = await session.execute(
            select(CexEarnRateRow).order_by(CexEarnRateRow.updated_at.desc())
        )
        seen: set[tuple[str, str, str]] = set()
        out: list[CexEarnRateRow] = []
        for row in result.scalars().all():
            key = (row.venue, row.asset, row.product_type)
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
        return out

async def list_cex_history(self, *, venue: str, asset: str,
                            since: datetime | None = None,
                            limit: int = 100) -> list[CexEarnRateRow]:
    async with self._session_factory() as session:
        q = select(CexEarnRateRow).where(
            CexEarnRateRow.venue == venue,
            CexEarnRateRow.asset == asset,
        )
        if since is not None:
            q = q.where(CexEarnRateRow.updated_at >= since)
        q = q.order_by(CexEarnRateRow.updated_at.desc()).limit(limit)
        result = await session.execute(q)
        return list(result.scalars().all())
```

Add `from datetime import datetime` if not already imported.

- [ ] **Step 9: Run all — verify green**

```bash
uv run pytest tests/models/test_cex_models.py tests/storage/test_cex_rates.py -v
```
Expected: 5 passed. Also run the full suite once to confirm no regressions:
```bash
uv run pytest tests/ -q
```
Expected: 392+ passed (existing count + 5 new).

- [ ] **Step 10: Commit**

```bash
git add src/stake_watch/models/cex.py src/stake_watch/storage/tables.py \
        src/stake_watch/storage/db.py tests/models/test_cex_models.py \
        tests/storage/test_cex_rates.py
git commit -m "feat(cex): models, ORM rows, and storage CRUD

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**Chunk 2 done when:** the two new tables exist in `Base.metadata`, `insert_cex_rates` / `list_latest_cex_rates` / `list_cex_history` are exercised by tests, and the full suite is green.

---

## Chunk 3: ConfigStore venue methods + seed extension

**Purpose:** Give the rest of the system a way to read and mutate the venue registry, and seed the five default venues on a fresh install (and on upgrade — an existing DB missing `cex_venues` still gets them).

**Files:**
- Modify: `src/stake_watch/storage/config_store.py`
- Modify: `config/seed.yaml`
- Create: `tests/storage/test_cex_venues.py`

- [ ] **Step 1: Write failing tests**

Create `tests/storage/test_cex_venues.py`:

```python
import json
import pytest
from stake_watch.storage.db import Storage
from stake_watch.storage.config_store import ConfigStore
from stake_watch.models.cex import CexVenue

@pytest.fixture
async def store():
    s = Storage("sqlite+aiosqlite:///:memory:")
    await s.initialize()
    yield ConfigStore(s._session_factory)
    await s.close()

@pytest.mark.asyncio
async def test_upsert_then_list(store):
    await store.upsert_cex_venue(CexVenue(name="okx", display_name="OKX"))
    rows = await store.list_cex_venues()
    assert len(rows) == 1 and rows[0].name == "okx"
    assert json.loads(rows[0].assets_json) == ["USDT", "USDC"]

@pytest.mark.asyncio
async def test_upsert_updates_and_bumps_updated_at(store):
    await store.upsert_cex_venue(CexVenue(name="okx", display_name="OKX"))
    first = (await store.list_cex_venues())[0].updated_at
    await store.upsert_cex_venue(CexVenue(name="okx", display_name="OKX Global"))
    row = (await store.list_cex_venues())[0]
    assert row.display_name == "OKX Global"
    assert row.updated_at >= first

@pytest.mark.asyncio
async def test_patch_toggles_enabled_and_assets(store):
    await store.upsert_cex_venue(CexVenue(name="okx", display_name="OKX"))
    await store.patch_cex_venue("okx", enabled=False, assets=["USDT"])
    row = (await store.list_cex_venues())[0]
    assert row.enabled is False
    assert json.loads(row.assets_json) == ["USDT"]

@pytest.mark.asyncio
async def test_list_enabled_filters(store):
    await store.upsert_cex_venue(CexVenue(name="okx", display_name="OKX"))
    await store.upsert_cex_venue(CexVenue(name="binance", display_name="Binance",
                                          enabled=False))
    enabled = await store.list_enabled_cex_venues()
    assert [v.name for v in enabled] == ["okx"]

@pytest.mark.asyncio
async def test_seed_is_idempotent_for_cex(store, tmp_path):
    seed = tmp_path / "seed.yaml"
    seed.write_text(
        "cex_venues:\n"
        "  - {name: okx, display_name: OKX, enabled: true, assets: [USDT, USDC]}\n"
    )
    await store.import_seed_if_empty(str(seed))
    await store.import_seed_if_empty(str(seed))  # second run must be a no-op
    assert len(await store.list_cex_venues()) == 1
```

- [ ] **Step 2: Run — verify fails**

```bash
uv run pytest tests/storage/test_cex_venues.py -v
```
Expected: AttributeError on `upsert_cex_venue`.

- [ ] **Step 3: Implement ConfigStore methods**

Add to `src/stake_watch/storage/config_store.py` (imports and methods):

```python
# top imports
from stake_watch.storage.tables import CexVenueRow  # noqa
from stake_watch.models.cex import CexVenue  # noqa

# inside class ConfigStore:
async def upsert_cex_venue(self, venue: CexVenue) -> CexVenueRow:
    async with self._sf() as s:
        now = datetime.now(timezone.utc)
        row = await s.get(CexVenueRow, venue.name)
        if row:
            row.display_name = venue.display_name
            row.enabled = venue.enabled
            row.assets_json = json.dumps(venue.assets)
            row.notes = venue.notes
            row.updated_at = now
        else:
            row = CexVenueRow(
                name=venue.name, display_name=venue.display_name,
                enabled=venue.enabled,
                assets_json=json.dumps(venue.assets),
                notes=venue.notes,
                created_at=now, updated_at=now,
            )
            s.add(row)
        await s.commit()
        await s.refresh(row)
        return row

async def list_cex_venues(self) -> list[CexVenueRow]:
    async with self._sf() as s:
        result = await s.execute(select(CexVenueRow).order_by(CexVenueRow.name))
        return list(result.scalars().all())

async def list_enabled_cex_venues(self) -> list[CexVenueRow]:
    async with self._sf() as s:
        result = await s.execute(
            select(CexVenueRow).where(CexVenueRow.enabled == True)  # noqa: E712
                              .order_by(CexVenueRow.name))
        return list(result.scalars().all())

async def patch_cex_venue(self, name: str, *, enabled: bool | None = None,
                          assets: list[str] | None = None,
                          notes: str | None = None) -> CexVenueRow | None:
    async with self._sf() as s:
        row = await s.get(CexVenueRow, name)
        if not row:
            return None
        if enabled is not None:
            row.enabled = enabled
        if assets is not None:
            row.assets_json = json.dumps(assets)
        if notes is not None:
            row.notes = notes
        row.updated_at = datetime.now(timezone.utc)
        await s.commit()
        await s.refresh(row)
        return row
```

Extend `import_seed_if_empty` — find the existing method and add a **separately gated** block at its bottom (mirrors the `existing = await self.list_protocols()` gate but for CEX):

```python
# ... existing seed body ...

# CEX venues — gated independently so upgrades from pre-CEX DBs still seed.
existing_cex = await self.list_cex_venues()
if not existing_cex:
    for entry in data.get("cex_venues", []):
        await self.upsert_cex_venue(CexVenue(**entry))
```

(`data` is the variable already used inside `import_seed_if_empty` for the parsed YAML dict — inspect the current implementation to match the exact name.)

- [ ] **Step 4: Run — verify passes**

```bash
uv run pytest tests/storage/test_cex_venues.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Update `config/seed.yaml`**

Append at the end of the file:

```yaml
cex_venues:
  - { name: binance, display_name: Binance, enabled: true, assets: [USDT, USDC] }
  - { name: okx,     display_name: OKX,     enabled: true, assets: [USDT, USDC] }
  - { name: bybit,   display_name: Bybit,   enabled: true, assets: [USDT, USDC] }
  - { name: gate,    display_name: Gate,    enabled: true, assets: [USDT, USDC] }
  - { name: bitget,  display_name: Bitget,  enabled: true, assets: [USDT, USDC] }
```

If Chunk 1 marked any venue "disabled" in the appendix, set its `enabled: false` here with a `notes:` field explaining why.

- [ ] **Step 6: Run full suite**

```bash
uv run pytest tests/ -q
```
Expected: 392+5+5 passed.

- [ ] **Step 7: Commit**

```bash
git add src/stake_watch/storage/config_store.py config/seed.yaml tests/storage/test_cex_venues.py
git commit -m "feat(cex): ConfigStore venue CRUD + seed defaults

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**Chunk 3 done when:** ConfigStore can upsert/list/enable-filter/patch venues, `import_seed_if_empty` seeds the five CEX venues on empty DBs (including upgrade scenarios), and tests are green.

---

## Chunk 4: Collector base + retry helper + registry

**Purpose:** Establish the shared plumbing every venue collector will use. Deliberately does *not* extract the DeFi retry helper — a small local copy is easier and avoids touching the 392-test-load-bearing `collectors/base.py`. That refactor is called out as "deferred" in the spec.

**Files:**
- Create: `src/stake_watch/collectors/cex/__init__.py`
- Create: `src/stake_watch/collectors/cex/base.py`
- Create: `src/stake_watch/collectors/cex/registry.py`
- Create: `tests/cex/test_base_retry.py`
- Create: `tests/cex/test_registry.py`

- [ ] **Step 1: Write failing tests for base**

Create `tests/cex/test_base_retry.py`:

```python
import pytest
from stake_watch.collectors.cex.base import CexEarnCollector
from stake_watch.models.cex import CexEarnRate
from datetime import datetime, timezone

class _FlakyThenOk(CexEarnCollector):
    venue = "flaky"
    _base_delay = 0.01  # fast tests
    def __init__(self):
        super().__init__(assets=["USDT"])
        self.calls = 0
    async def fetch(self):
        self.calls += 1
        if self.calls < 3:
            raise RuntimeError("429 too many requests")
        return [CexEarnRate(venue="flaky", asset="USDT",
                            apy_min=0.05, apy_max=0.05,
                            updated_at=datetime.now(timezone.utc))]

class _AlwaysBroken(CexEarnCollector):
    venue = "broken"
    _base_delay = 0.01
    async def fetch(self): raise RuntimeError("500 server error")

class _NotRateLimit(CexEarnCollector):
    venue = "hard"
    _base_delay = 0.01
    def __init__(self):
        super().__init__(assets=["USDT"])
        self.calls = 0
    async def fetch(self):
        self.calls += 1
        raise ValueError("bad JSON")

@pytest.mark.asyncio
async def test_retries_on_429_then_succeeds():
    c = _FlakyThenOk()
    snap = await c.collect()
    assert snap.errors == [] and len(snap.rates) == 1
    assert c.calls == 3

@pytest.mark.asyncio
async def test_500_lands_in_errors():
    snap = await _AlwaysBroken().collect()
    assert snap.rates == [] and len(snap.errors) == 1
    assert "500" in snap.errors[0]

@pytest.mark.asyncio
async def test_non_rate_limit_does_not_retry():
    c = _NotRateLimit()
    snap = await c.collect()
    assert snap.rates == [] and c.calls == 1
    assert "bad JSON" in snap.errors[0]
```

- [ ] **Step 2: Run — verify fails**

```bash
uv run pytest tests/cex/test_base_retry.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `collectors/cex/base.py`**

```python
from __future__ import annotations
import asyncio, logging, random
from abc import ABC, abstractmethod
from stake_watch.models.cex import CexEarnRate, VenueRateSnapshot

_CEX_MAX_CONCURRENCY = 3
_venue_semaphore = asyncio.Semaphore(_CEX_MAX_CONCURRENCY)

def _looks_like_rate_limit(err: BaseException) -> bool:
    s = str(err).lower()
    return "429" in s or "too many requests" in s or "rate limit" in s

class CexEarnCollector(ABC):
    venue: str = "unknown"
    _retries = 3
    _base_delay = 2.0

    def __init__(self, assets: list[str]):
        self.assets = [a.upper() for a in assets]
        self.logger = logging.getLogger(f"cex.{self.venue}")

    @abstractmethod
    async def fetch(self) -> list[CexEarnRate]: ...

    async def collect(self) -> VenueRateSnapshot:
        async with _venue_semaphore:
            try:
                rates = await self._with_retry(self.fetch)
                return VenueRateSnapshot(venue=self.venue, rates=rates)
            except Exception as e:
                self.logger.warning("%s: fetch failed: %s", self.venue, e)
                return VenueRateSnapshot(venue=self.venue, rates=[], errors=[str(e)])

    async def _with_retry(self, fn):
        last: BaseException | None = None
        for attempt in range(self._retries):
            try:
                return await fn()
            except Exception as e:
                last = e
                if not _looks_like_rate_limit(e):
                    raise
                if attempt == self._retries - 1:
                    break
                delay = self._base_delay * (2 ** attempt) + random.uniform(0, 1)
                self.logger.warning("%s: rate-limited, backing off %.1fs (%d/%d)",
                                    self.venue, delay, attempt + 1, self._retries)
                await asyncio.sleep(delay)
        assert last is not None
        raise last
```

Create empty `src/stake_watch/collectors/cex/__init__.py`.

- [ ] **Step 4: Verify base tests pass**

```bash
uv run pytest tests/cex/test_base_retry.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Write failing test for registry**

Create `tests/cex/test_registry.py`:

```python
from stake_watch.collectors.cex.registry import build_cex_collector
from stake_watch.models.cex import CexVenue

def _v(name):
    return CexVenue(name=name, display_name=name.upper())

def test_all_five_resolve():
    for n in ("binance", "okx", "bybit", "gate", "bitget"):
        c = build_cex_collector(_v(n))
        assert c is not None and c.venue == n

def test_unknown_returns_none():
    assert build_cex_collector(_v("nonesuch")) is None
```

- [ ] **Step 6: Run — verify fails**

```bash
uv run pytest tests/cex/test_registry.py -v
```
Expected: ImportError (module missing).

- [ ] **Step 7: Implement `collectors/cex/registry.py` (skeleton — venue classes come in Chunk 5)**

```python
from __future__ import annotations
from stake_watch.collectors.cex.base import CexEarnCollector
from stake_watch.models.cex import CexVenue

def build_cex_collector(venue: CexVenue) -> CexEarnCollector | None:
    match venue.name:
        case "binance":
            from stake_watch.collectors.cex.binance import BinanceEarnCollector
            return BinanceEarnCollector(venue.assets)
        case "okx":
            from stake_watch.collectors.cex.okx import OkxEarnCollector
            return OkxEarnCollector(venue.assets)
        case "bybit":
            from stake_watch.collectors.cex.bybit import BybitEarnCollector
            return BybitEarnCollector(venue.assets)
        case "gate":
            from stake_watch.collectors.cex.gate import GateEarnCollector
            return GateEarnCollector(venue.assets)
        case "bitget":
            from stake_watch.collectors.cex.bitget import BitgetEarnCollector
            return BitgetEarnCollector(venue.assets)
        case _:
            return None
```

Registry test in Step 5 will still fail (venue modules don't exist yet) — that's fine, it becomes the driver for Chunk 5. Skip the registry test with `@pytest.mark.skip("wired in chunk 5")` for now, or move it to Chunk 5. Cleanest: leave the file, mark `test_all_five_resolve` skipped, land Chunk 5 that un-skips it.

Change `tests/cex/test_registry.py`:

```python
import pytest

@pytest.mark.skip(reason="unskipped by chunk 5 once venue modules exist")
def test_all_five_resolve():
    ...
```

- [ ] **Step 8: Confirm suite is green**

```bash
uv run pytest tests/ -q
```
Expected: full suite green (5 previous + 3 base + 1 skipped = 4 new).

- [ ] **Step 9: Commit**

```bash
git add src/stake_watch/collectors/cex/ tests/cex/test_base_retry.py tests/cex/test_registry.py
git commit -m "feat(cex): base collector + retry + registry skeleton

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**Chunk 4 done when:** `CexEarnCollector` ABC + retry helper + registry are in place, base retries and error swallowing are covered by tests.

---

## Chunk 5: Per-venue collectors

**Purpose:** Implement the five venue-specific `fetch()` methods, driven by the fixtures captured in Chunk 1. **Order matters:** the appendix in Chunk 1 established which venues work directly and which need scraping / disabling. Follow that order — OKX first, hardest last.

Any venue that Chunk 1 marked as unreachable ships with a stub `fetch()` that raises `NotImplementedError` and stays `enabled: false` in seed. The registry still resolves it (so tests match reality); it just won't be exercised at runtime.

**Files (one implementation + one test file per venue):**
- Create: `src/stake_watch/collectors/cex/okx.py`, `binance.py`, `bybit.py`, `gate.py`, `bitget.py`
- Create: `tests/cex/test_okx_collector.py`, `test_binance_collector.py`, `test_bybit_collector.py`, `test_gate_collector.py`, `test_bitget_collector.py`

**Follow @superpowers:test-driven-development strictly for every venue: fixture → assertion → parser.**

- [ ] **Step 1: OKX — write failing test**

Create `tests/cex/test_okx_collector.py`. Load `tests/cex/fixtures/okx_earn.json` (shape from Chunk 1: `{"USDT": <resp>, "USDC": <resp>}`), mock `httpx.AsyncClient.get` to return the right body per URL:

```python
import json, pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from stake_watch.collectors.cex.okx import OkxEarnCollector

FIX = json.loads((Path(__file__).parent / "fixtures/okx_earn.json").read_text())

class _Resp:
    def __init__(self, body): self._b = body
    def raise_for_status(self): pass
    def json(self): return self._b

@pytest.mark.asyncio
async def test_okx_parses_usdt_and_usdc():
    async def _get(url, **kw):
        if "USDT" in url: return _Resp(FIX["USDT"])
        if "USDC" in url: return _Resp(FIX["USDC"])
        raise AssertionError(url)
    with patch("httpx.AsyncClient") as MC:
        client = MC.return_value.__aenter__.return_value
        client.get = AsyncMock(side_effect=_get)
        rates = await OkxEarnCollector(["USDT","USDC"]).fetch()
    assets = {r.asset for r in rates}
    assert assets == {"USDT","USDC"}
    for r in rates:
        assert r.apy_min > 0 and r.apy_max >= r.apy_min
        assert r.product_type == "flexible" and r.venue == "okx"
```

- [ ] **Step 2: Run — verify fails**

```bash
uv run pytest tests/cex/test_okx_collector.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `collectors/cex/okx.py`**

The exact JSON key path depends on what the Chunk 1 fixture actually contains — inspect the fixture, then pull the field. Sketch (adjust field names to match reality):

```python
from __future__ import annotations
import json
from datetime import datetime, timezone
import httpx
from stake_watch.collectors.cex.base import CexEarnCollector
from stake_watch.models.cex import CexEarnRate

URL = "https://www.okx.com/api/v5/finance/savings/lending-rate-summary?ccy={ccy}"

class OkxEarnCollector(CexEarnCollector):
    venue = "okx"

    async def fetch(self) -> list[CexEarnRate]:
        now = datetime.now(timezone.utc)
        out: list[CexEarnRate] = []
        async with httpx.AsyncClient(timeout=20) as c:
            for asset in self.assets:
                r = await c.get(URL.format(ccy=asset))
                r.raise_for_status()
                body = r.json()
                # OKX summary shape: {"code":"0","data":[{"ccy":"USDT","estRate":"0.04"}]}
                entry = (body.get("data") or [{}])[0]
                rate = float(entry.get("estRate") or 0)
                if rate <= 0:
                    continue
                out.append(CexEarnRate(
                    venue=self.venue, asset=asset,
                    apy_min=rate, apy_max=rate,
                    tier_note=None,
                    raw_json=json.dumps(entry),
                    updated_at=now))
        return out
```

- [ ] **Step 4: Run — verify passes**

```bash
uv run pytest tests/cex/test_okx_collector.py -v
```
Expected: 1 passed.

- [ ] **Step 5: Commit OKX**

```bash
git add src/stake_watch/collectors/cex/okx.py tests/cex/test_okx_collector.py
git commit -m "feat(cex): OKX flexible-savings collector

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Repeat steps 1–5 for the remaining four venues**

For each of `bitget`, `bybit`, `gate`, `binance` (in the order established by Chunk 1's spike):

  - [ ] Write `tests/cex/test_<venue>_collector.py` following the OKX pattern. Assertions:
    - USDT and USDC rows both appear (unless the venue only serves one — noted in Chunk 1).
    - `apy_min <= apy_max`, both positive.
    - `apy_min < apy_max` when the fixture is tiered; `tier_note` non-empty.
    - `apy_min == apy_max` and `tier_note is None` when the fixture is a single rate.
  - [ ] Run the test, watch it fail.
  - [ ] Implement `collectors/cex/<venue>.py`. URL and JSON path as module constants. Tiered parsing (Binance, Bitget, Bybit) uses `min()` and `max()` over the tier array; untiered (OKX) sets both equal.
  - [ ] Run the test, watch it pass.
  - [ ] Commit.

For any venue Chunk 1 marked "disabled":

```python
# src/stake_watch/collectors/cex/<venue>.py
from stake_watch.collectors.cex.base import CexEarnCollector
from stake_watch.models.cex import CexEarnRate

class _EarnCollectorStub(CexEarnCollector):
    venue = "<venue>"
    async def fetch(self) -> list[CexEarnRate]:
        raise NotImplementedError("public endpoint unavailable — see spec appendix")
```

Its test asserts `NotImplementedError` from `fetch()` and that `collect()` swallows it into `errors`.

- [ ] **Step 7: Un-skip the registry test**

Remove the `@pytest.mark.skip(...)` decorator from `tests/cex/test_registry.py` and run:

```bash
uv run pytest tests/cex/test_registry.py -v
```
Expected: 2 passed.

- [ ] **Step 8: Full-suite verification**

```bash
uv run pytest tests/ -q
```
Expected: 392 baseline + ~15 new tests, all green. Paste the summary line into the commit body.

- [ ] **Step 9: Commit — final of chunk**

```bash
git add tests/cex/test_registry.py
git commit -m "test(cex): un-skip registry test now that all venues exist

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**Chunk 5 done when:** every venue in seed either produces real `CexEarnRate` rows against its captured fixture, or is a documented stub that Chunk 1 authorised. Registry test passes without skip.

---

## Chunk 6: Scheduler wiring

**Purpose:** Add the `_refresh_cex_rates` coroutine, expose `cex_rates_interval` on `ScheduledRunner`, wire `main.py` to read `cex.refresh_interval` from the config store, and schedule the first run immediately so `/cex` isn't blank on first launch.

**Files:**
- Modify: `src/stake_watch/scheduler/runner.py`
- Modify: `src/stake_watch/main.py`
- Create: `tests/scheduler/test_cex_job.py`

- [ ] **Step 1: Write failing test**

Create `tests/scheduler/test_cex_job.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone
from stake_watch.storage.db import Storage
from stake_watch.storage.config_store import ConfigStore
from stake_watch.models.cex import CexVenue, CexEarnRate, VenueRateSnapshot
from stake_watch.scheduler.runner import ScheduledRunner, CollectionRunner

@pytest.fixture
async def wired():
    s = Storage("sqlite+aiosqlite:///:memory:")
    await s.initialize()
    store = ConfigStore(s._session_factory)
    await store.upsert_cex_venue(CexVenue(name="okx", display_name="OKX"))
    await store.upsert_cex_venue(CexVenue(name="binance", display_name="Binance"))
    cr = CollectionRunner(config_store=store, storage=s, wallets=[],
                          rpc_urls={}, notifier=None, risk_evaluator=None)
    runner = ScheduledRunner(collection_runner=cr, storage=s, cex_rates_interval=1)
    yield runner, s, store
    await s.close()

@pytest.mark.asyncio
async def test_refresh_writes_rates_and_swallows_errors(wired):
    runner, s, store = wired
    now = datetime.now(timezone.utc)
    okx_ok = VenueRateSnapshot(venue="okx", rates=[
        CexEarnRate(venue="okx", asset="USDT", apy_min=0.04, apy_max=0.04,
                    updated_at=now)])
    binance_fail = VenueRateSnapshot(venue="binance", rates=[], errors=["boom"])

    def _fake_build(v):
        m = AsyncMock()
        m.collect = AsyncMock(return_value=okx_ok if v.name == "okx" else binance_fail)
        return m

    with patch("stake_watch.scheduler.runner.build_cex_collector", side_effect=_fake_build):
        await runner._refresh_cex_rates()

    latest = await s.list_latest_cex_rates()
    assert len(latest) == 1 and latest[0].venue == "okx"
```

- [ ] **Step 2: Run — verify fails**

```bash
uv run pytest tests/scheduler/test_cex_job.py -v
```
Expected: AttributeError on `_refresh_cex_rates` or on `cex_rates_interval`.

- [ ] **Step 3: Add scheduler hook**

Modify `src/stake_watch/scheduler/runner.py`:

1. Add `cex_rates_interval: int = 1800` to `ScheduledRunner.__init__` args and stash it on `self`.
2. Add the coroutine (place next to `_refresh_dex_liquidity`):

```python
async def _refresh_cex_rates(self):
    if not self.storage:
        return
    try:
        from stake_watch.collectors.cex.registry import build_cex_collector
        from stake_watch.storage.config_store import ConfigStore
        import asyncio
        store = ConfigStore(self.storage._session_factory)
        venues = await store.list_enabled_cex_venues()
        pairs = []
        for v in venues:
            # ConfigStore returns rows; adapt to the CexVenue pydantic model
            from stake_watch.models.cex import CexVenue
            import json as _json
            venue_model = CexVenue(
                name=v.name, display_name=v.display_name,
                enabled=v.enabled,
                assets=_json.loads(v.assets_json or "[]") or ["USDT","USDC"],
                notes=v.notes,
            )
            collector = build_cex_collector(venue_model)
            if collector is not None:
                pairs.append((venue_model, collector))
        snaps = await asyncio.gather(*(c.collect() for _, c in pairs))
        for snap in snaps:
            if snap.rates:
                await self.storage.insert_cex_rates(snap.rates)
            for err in snap.errors:
                logger.warning("cex[%s]: %s", snap.venue, err)
    except Exception as e:
        logger.error(f"CEX rates refresh failed: {e}")
```

3. In `start()`, next to the other conditional `add_job` blocks, add:

```python
if self.cex_rates_interval > 0 and self.storage:
    from datetime import datetime, timezone
    self._scheduler.add_job(self._refresh_cex_rates,
        trigger=IntervalTrigger(seconds=self.cex_rates_interval),
        id="cex_rates", name="CEX Earn rates",
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc))  # immediate first run
    logger.info(f"CEX rates every {self.cex_rates_interval}s")
```

- [ ] **Step 4: Run — verify passes**

```bash
uv run pytest tests/scheduler/test_cex_job.py -v
```
Expected: 1 passed.

- [ ] **Step 5: Wire `main.py`**

In `src/stake_watch/main.py`, alongside the other `get_setting(...) or <default>` reads:

```python
cex_rates_interval = await config_store.get_setting("cex.refresh_interval") or 1800
```

Pass it into `ScheduledRunner(...)`:

```python
scheduled = ScheduledRunner(
    ...,
    cex_rates_interval=cex_rates_interval,
)
```

- [ ] **Step 6: Sanity — run the app end-to-end for 30 seconds**

```bash
uv run python -m stake_watch.main &
SW_PID=$!
sleep 30
kill $SW_PID
```

Watch logs. Expected line: `CEX rates every 1800s` at startup and one `_refresh_cex_rates` execution (from `next_run_time=now`). Any per-venue failures show as `WARNING cex[<venue>]: …` and do not abort the process.

Then verify data landed:

```bash
uv run python -c "
import asyncio; from stake_watch.storage.db import Storage
async def go():
    s = Storage('sqlite+aiosqlite:///stake_watch.db')
    print(len(await s.list_latest_cex_rates()), 'CEX rate rows')
asyncio.run(go())
"
```

Expected: a positive integer (however many venue×asset pairs actually returned data — could be as low as 2 if only OKX works).

- [ ] **Step 7: Commit**

```bash
git add src/stake_watch/scheduler/runner.py src/stake_watch/main.py tests/scheduler/test_cex_job.py
git commit -m "feat(cex): scheduler job + main.py wiring with immediate first run

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**Chunk 6 done when:** the scheduler starts a `cex_rates` job, first run fires immediately, per-venue failures are logged not raised, and a manual run populates `cex_earn_rates`.

---

## Chunk 7: FastAPI router

**Purpose:** Expose venue management + rate lookup at `/api/cex/*`.

**Files:**
- Create: `src/stake_watch/api/routes/cex.py`
- Modify: `src/stake_watch/api/app.py` (one `include_router` line)
- Create: `tests/api/test_cex_endpoints.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/test_cex_endpoints.py`. Match how other route tests build a `TestClient` — inspect e.g. `tests/api/test_protocols.py` for the fixture wiring pattern:

```python
import pytest
from httpx import AsyncClient
from datetime import datetime, timezone
from stake_watch.models.cex import CexVenue, CexEarnRate
# ... use the same app/storage/config_store fixture as other API tests ...

@pytest.mark.asyncio
async def test_list_venues(client, config_store):
    await config_store.upsert_cex_venue(CexVenue(name="okx", display_name="OKX"))
    r = await client.get("/api/cex/venues")
    assert r.status_code == 200
    body = r.json()
    assert body[0]["name"] == "okx" and body[0]["assets"] == ["USDT","USDC"]

@pytest.mark.asyncio
async def test_patch_venue_toggles_enabled(client, config_store):
    await config_store.upsert_cex_venue(CexVenue(name="okx", display_name="OKX"))
    r = await client.patch("/api/cex/venues/okx", json={"enabled": False})
    assert r.status_code == 200
    assert (await config_store.list_cex_venues())[0].enabled is False

@pytest.mark.asyncio
async def test_patch_unknown_venue_returns_404(client):
    r = await client.patch("/api/cex/venues/nonesuch", json={"enabled": False})
    assert r.status_code == 404

@pytest.mark.asyncio
async def test_latest_rates(client, storage, config_store):
    await config_store.upsert_cex_venue(CexVenue(name="okx", display_name="OKX"))
    now = datetime.now(timezone.utc)
    await storage.insert_cex_rates([
        CexEarnRate(venue="okx", asset="USDT", apy_min=0.04, apy_max=0.05,
                    tier_note="0-500: 5%; 500+: 4%", updated_at=now)
    ])
    r = await client.get("/api/cex/rates/latest")
    assert r.status_code == 200
    row = r.json()[0]
    assert row["venue"] == "okx" and row["venue_display"] == "OKX"
    assert row["apy_min"] == 0.04 and row["apy_max"] == 0.05
    assert "raw_json" not in row   # never surfaced by API

@pytest.mark.asyncio
async def test_history_endpoint_filters(client, storage):
    now = datetime.now(timezone.utc)
    await storage.insert_cex_rates([
        CexEarnRate(venue="okx", asset="USDT", apy_min=0.03, apy_max=0.03,
                    updated_at=now)])
    r = await client.get("/api/cex/rates/history?venue=okx&asset=USDT")
    assert r.status_code == 200 and len(r.json()) == 1
```

- [ ] **Step 2: Run — verify fails**

```bash
uv run pytest tests/api/test_cex_endpoints.py -v
```
Expected: 404 or ImportError.

- [ ] **Step 3: Implement `api/routes/cex.py`**

```python
from __future__ import annotations
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from stake_watch.api.deps import get_config_store, get_storage
from stake_watch.models.cex import CexVenue
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage

router = APIRouter()

class VenueOut(BaseModel):
    name: str
    display_name: str
    enabled: bool
    assets: list[str]
    notes: str | None = None

class VenuePatch(BaseModel):
    enabled: bool | None = None
    assets: list[str] | None = None
    notes: str | None = None

class RateOut(BaseModel):
    venue: str
    venue_display: str
    asset: str
    product_type: str
    apy_min: float
    apy_max: float
    tier_note: str | None
    updated_at: datetime

def _venue_out(row) -> VenueOut:
    return VenueOut(
        name=row.name, display_name=row.display_name, enabled=row.enabled,
        assets=json.loads(row.assets_json or "[]") or ["USDT","USDC"],
        notes=row.notes,
    )

@router.get("/venues", response_model=list[VenueOut])
async def list_venues(store: ConfigStore = Depends(get_config_store)):
    return [_venue_out(r) for r in await store.list_cex_venues()]

@router.patch("/venues/{name}", response_model=VenueOut)
async def patch_venue(name: str, body: VenuePatch,
                      store: ConfigStore = Depends(get_config_store)):
    row = await store.patch_cex_venue(name, enabled=body.enabled,
                                      assets=body.assets, notes=body.notes)
    if not row:
        raise HTTPException(404, f"venue '{name}' not found")
    return _venue_out(row)

@router.get("/rates/latest", response_model=list[RateOut])
async def latest_rates(storage: Storage = Depends(get_storage),
                       store: ConfigStore = Depends(get_config_store)):
    venues = {v.name: v.display_name for v in await store.list_cex_venues()}
    rows = await storage.list_latest_cex_rates()
    out = []
    for r in rows:
        out.append(RateOut(
            venue=r.venue, venue_display=venues.get(r.venue, r.venue),
            asset=r.asset, product_type=r.product_type,
            apy_min=r.apy_min, apy_max=r.apy_max,
            tier_note=r.tier_note, updated_at=r.updated_at,
        ))
    return sorted(out, key=lambda x: x.apy_max, reverse=True)

@router.get("/rates/history", response_model=list[RateOut])
async def history_rates(venue: str, asset: str, since: datetime | None = None,
                        limit: int = 100,
                        storage: Storage = Depends(get_storage),
                        store: ConfigStore = Depends(get_config_store)):
    venues = {v.name: v.display_name for v in await store.list_cex_venues()}
    rows = await storage.list_cex_history(venue=venue, asset=asset,
                                          since=since, limit=limit)
    return [RateOut(
        venue=r.venue, venue_display=venues.get(r.venue, r.venue),
        asset=r.asset, product_type=r.product_type,
        apy_min=r.apy_min, apy_max=r.apy_max,
        tier_note=r.tier_note, updated_at=r.updated_at,
    ) for r in rows]
```

Register in `src/stake_watch/api/app.py` after the other `include_router` lines:

```python
from stake_watch.api.routes import cex  # top
...
app.include_router(cex.router, prefix="/api/cex", tags=["cex"])
```

- [ ] **Step 4: Run — verify passes**

```bash
uv run pytest tests/api/test_cex_endpoints.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Full-suite check**

```bash
uv run pytest tests/ -q
```

- [ ] **Step 6: Commit**

```bash
git add src/stake_watch/api/routes/cex.py src/stake_watch/api/app.py tests/api/test_cex_endpoints.py
git commit -m "feat(cex): /api/cex/* router (venues + latest/history rates)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**Chunk 7 done when:** `/api/cex/venues`, PATCH, `/rates/latest`, `/rates/history` all return correctly-shaped data and 404 on unknown venue.

---

## Chunk 8: Frontend `/cex` page

**Purpose:** Ship the `/cex` tab: a sortable table of latest venue×asset APYs plus a Manage-venues collapsible section.

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/api/cex.ts`
- Create: `frontend/src/pages/Cex.tsx`

Study `frontend/src/api/protocols.ts` and `frontend/src/pages/Protocols.tsx` first so the new files match the codebase's actual React style. The snippets below are structural; adapt to the styling/data-fetching conventions already in use.

- [ ] **Step 1: API client — `frontend/src/api/cex.ts`**

```ts
export type CexVenue = {
  name: string;
  display_name: string;
  enabled: boolean;
  assets: string[];
  notes: string | null;
};

export type CexRate = {
  venue: string;
  venue_display: string;
  asset: string;
  product_type: string;
  apy_min: number;
  apy_max: number;
  tier_note: string | null;
  updated_at: string;
};

const base = '/api/cex';

export async function listVenues(): Promise<CexVenue[]> {
  const r = await fetch(`${base}/venues`);
  if (!r.ok) throw new Error(`venues ${r.status}`);
  return r.json();
}

export async function patchVenue(name: string,
    body: Partial<Pick<CexVenue, 'enabled' | 'assets' | 'notes'>>): Promise<CexVenue> {
  const r = await fetch(`${base}/venues/${name}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`patch ${r.status}`);
  return r.json();
}

export async function latestRates(): Promise<CexRate[]> {
  const r = await fetch(`${base}/rates/latest`);
  if (!r.ok) throw new Error(`latest ${r.status}`);
  return r.json();
}
```

- [ ] **Step 2: Page — `frontend/src/pages/Cex.tsx`**

Follows the Protocols page pattern (useEffect fetch, useState, minimal component). Skeleton:

```tsx
import { useEffect, useMemo, useState } from 'react';
import { listVenues, patchVenue, latestRates, CexVenue, CexRate } from '../api/cex';

const pct = (x: number) => (x * 100).toFixed(2) + '%';
const rangeText = (r: CexRate) =>
  r.apy_min === r.apy_max ? pct(r.apy_max) : `${pct(r.apy_min)}–${pct(r.apy_max)}`;
const minAgo = (iso: string) => Math.round((Date.now() - Date.parse(iso)) / 60000);

export function Cex() {
  const [rates, setRates] = useState<CexRate[]>([]);
  const [venues, setVenues] = useState<CexVenue[]>([]);
  const [sortDesc, setSortDesc] = useState(true);
  const [manageOpen, setManageOpen] = useState(false);

  const refresh = () => {
    latestRates().then(setRates).catch(console.error);
    listVenues().then(setVenues).catch(console.error);
  };
  useEffect(refresh, []);

  const oldest = useMemo(
    () => rates.length ? Math.max(...rates.map(r => minAgo(r.updated_at))) : null,
    [rates]);

  const sorted = useMemo(
    () => [...rates].sort((a, b) =>
      (b.apy_max - a.apy_max) * (sortDesc ? 1 : -1)),
    [rates, sortDesc]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">CEX Earn 利率</h1>
        <span className="text-sm text-gray-400">
          {oldest !== null ? `${oldest} 分钟前刷新` : '暂无数据'}
        </span>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-gray-400 border-b border-gray-800">
            <th className="py-2">Venue</th>
            <th>Asset</th>
            <th className="cursor-pointer" onClick={() => setSortDesc(s => !s)}>
              Flexible APY {sortDesc ? '▼' : '▲'}
            </th>
            <th>分档</th>
            <th>Updated</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map(r => (
            <tr key={`${r.venue}-${r.asset}-${r.product_type}`}
                className="border-b border-gray-900">
              <td className="py-2">{r.venue_display}</td>
              <td>{r.asset}</td>
              <td className="font-mono">{rangeText(r)}</td>
              <td title={r.tier_note ?? ''}>
                {r.tier_note ? '…' : '—'}
              </td>
              <td className="text-gray-500">{minAgo(r.updated_at)}m ago</td>
            </tr>
          ))}
        </tbody>
      </table>

      <button onClick={() => setManageOpen(o => !o)}
              className="text-sm text-blue-400">
        {manageOpen ? '收起' : '管理 venues'}
      </button>

      {manageOpen && (
        <div className="space-y-2 border-t border-gray-800 pt-4">
          {venues.map(v => (
            <label key={v.name} className="flex items-center gap-3">
              <input type="checkbox" checked={v.enabled} onChange={async e => {
                await patchVenue(v.name, { enabled: e.target.checked });
                refresh();
              }} />
              <span className="w-28">{v.display_name}</span>
              <span className="text-gray-500 text-sm">{v.assets.join(', ')}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Wire into `App.tsx`**

- Import `Cex`.
- Add `<NavLink to="/cex" …>CEX</NavLink>` alongside the existing `/stablecoins` link (Chinese label `CEX 利率`).
- Add `<Route path="/cex" element={<Cex />} />` to the `<Routes>`.

- [ ] **Step 4: Manual smoke test**

```bash
uv run python -m stake_watch.main &
(cd frontend && npm run dev) &
```

Wait ~30s (first CEX refresh), then open `http://localhost:5173/cex`.

**Verify:**
- Rates table populated with at least the venues Chunk 1 confirmed working.
- Sorting toggle changes order.
- Hovering the "分档" cell shows `tier_note` for tiered rows.
- Toggling a venue in Manage → checkbox persists (refetch shows same value).
- Toggling to `false` and waiting for the next refresh cycle removes that venue's rows.

Kill both processes.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/api/cex.ts frontend/src/pages/Cex.tsx
git commit -m "feat(cex): /cex React page + nav wiring

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**Chunk 8 done when:** the `/cex` tab renders live data end-to-end from a running backend.

---

## Chunk 9: Final verification + docs

**Purpose:** Full-suite green, coverage numbers recorded, CLAUDE.md hint added if useful, branch ready for the finishing-a-branch flow.

- [ ] **Step 1: Full test run with coverage**

```bash
uv run pytest tests/ --cov=stake_watch --cov-report=term-missing -q
```

Expected: existing 392 + ~20 new tests pass; overall project coverage ≥ 80%; new `stake_watch/collectors/cex/`, `stake_watch/models/cex.py`, and `stake_watch/api/routes/cex.py` coverage ≥ 90%. If a venue file is a stub (Chunk 5), its coverage may be lower — that's expected.

- [ ] **Step 2: End-to-end smoke — one full cycle**

```bash
uv run python -m stake_watch.main &
SW_PID=$!
sleep 60
kill $SW_PID
```

Then:

```bash
uv run python -c "
import asyncio; from stake_watch.storage.db import Storage
async def go():
    s = Storage('sqlite+aiosqlite:///stake_watch.db')
    for r in await s.list_latest_cex_rates():
        print(r.venue, r.asset, r.apy_min, r.apy_max)
asyncio.run(go())
"
```

Expected: at least one row printed. Paste output into the PR description.

- [ ] **Step 3: Update project doc**

Append one line under **Directory Structure** in `CLAUDE.md`:

```
  cex/             # CEX Earn rate collectors (Binance/OKX/Bybit/Gate/Bitget)
```

- [ ] **Step 4: Commit doc**

```bash
git add CLAUDE.md
git commit -m "docs: mention new collectors/cex/ subsystem

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 5: Follow @superpowers:finishing-a-development-branch**

Choose merge vs PR based on the user's preference at the time. Do not merge to `main` until the smoke test in Step 2 actually produced data.

**Plan complete when:** full pytest suite green, /cex page shows real venue data, branch is either merged or on a reviewable PR.