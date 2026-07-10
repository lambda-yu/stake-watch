# CEX Earn Collectors — Design Spec

**Date:** 2026-07-10
**Status:** Draft v2 (post-review)
**Scope:** Add centralized-exchange USDT/USDC flexible-earn APY collection alongside the existing DeFi protocol monitoring.

## Goal

Show current USDT/USDC "Simple Earn" / "Flexible Savings" rates from the top CEXes (Binance, OKX, Bybit, Gate, Bitget) in a dedicated `/cex` tab, so the user can compare CEX yields against DeFi protocols already tracked. Public endpoints only — no API keys, no account-balance tracking, no Telegram alerts.

## Non-goals

- Positions / account tracking (no API keys in this iteration).
- Fixed-term / locked / structured / launchpool / auto-invest products (flexible only).
- Risk scoring, safety_rank, or depeg/APY-change alerts on CEX rates.
- Historical charts in the UI (history endpoint is provisioned; charting deferred).

## Design decisions

- **New parallel subsystem, split across the existing standard folders (not a single "mirror stablecoin/" subtree).** CEX venues have no chain, no TVL, no pool address, no utilization — treating them as `ProtocolEntry` rows pollutes DeFi semantics. Instead, follow the split-across-standard-folders convention already used by stablecoin code: collectors under `collectors/cex/`, models in `models/cex.py`, ORM rows in `storage/tables.py`, storage methods in `storage/db.py`, router in `api/routes/cex.py`, React page under `frontend/src/pages/`.
- **Both lowest and highest tier APY are stored** (`apy_min`, `apy_max`). Most CEX flexible products stack tiers ("0–500 USDT: 8%, 500+: 4.25%"). Two columns cost nothing now and avoid a future migration; UI renders `apy_min` when untiered (min==max) and `min–max` otherwise. Full tier breakdown is kept in a `tier_note` string for tooltip use.
- **Independent refresh interval** (`cex.refresh_interval`, default 1800s / 30 min). Rates change slowly; no need to hit five CEX APIs at DeFi cadence. User-editable from Settings UI via the existing `get_setting`/`set_setting` path in `ConfigStore`.
- **Failures are silent to Telegram.** Per-venue errors go to logs + a stored `errors` list on the snapshot; no alert path.
- **No new chains.** The `Chain` enum is not extended. CEX venues live in a separate `cex_venues` table, not in the `protocol_configs` table.
- **`float`, not `Decimal`, for APYs.** Matches how `stablecoin_metrics` stores rates; APY precision to ~6 float digits is fine.

## Architecture — file layout

```
src/stake_watch/
  collectors/cex/                    # NEW
    __init__.py
    base.py                          # CexEarnCollector ABC (own retry helper)
    binance.py
    okx.py
    bybit.py
    gate.py
    bitget.py
    registry.py                      # venue name -> collector class
  models/cex.py                      # NEW: CexEarnRate, VenueRateSnapshot, CexVenue
  storage/
    tables.py                        # EDIT: add CexEarnRateRow, CexVenueRow
    db.py                            # EDIT: add insert_cex_rates, list_latest_cex_rates, list_cex_history
    config_store.py                  # EDIT: extend import_seed_if_empty for cex_venues; list/patch venue methods
  api/
    app.py                           # EDIT: include_router for cex
    routes/cex.py                    # NEW: /api/cex/* endpoints
  scheduler/runner.py                # EDIT: cex_rates_interval + _refresh_cex_rates
  main.py                            # EDIT: read cex.refresh_interval, pass to ScheduledRunner
config/seed.yaml                     # EDIT: cex_venues block + cex.refresh_interval
frontend/src/
  App.tsx                            # EDIT: add /cex route + nav link (matches Protocols/Settings)
  pages/Cex.tsx                      # NEW
  api/                               # EDIT: cex client
tests/
  cex/                               # NEW: collector unit tests + fixtures
  storage/test_cex_rates.py          # NEW
  api/test_cex_endpoints.py          # NEW
  scheduler/test_cex_job.py          # NEW
```

## Data flow

```
scheduler tick (every cex.refresh_interval)
  -> config_store.list_enabled_cex_venues()
  -> for each venue in parallel:
       build_cex_collector(venue).collect()
         -> fetch()                    # HTTP call to public endpoint
         -> parse -> [CexEarnRate...]
         -> wrap in VenueRateSnapshot(rates=..., errors=...)
  -> storage.insert_cex_rates(snap.rates) per snapshot
  -> log warnings for snap.errors
```

The DeFi collector path, positions path, risk engine, and Telegram notifier are untouched.

## Data model

### Pydantic — `src/stake_watch/models/cex.py`

```python
class CexEarnRate(BaseModel):
    venue: str                    # "binance" | "okx" | "bybit" | "gate" | "bitget"
    asset: str                    # "USDT" | "USDC"
    product_type: str = "flexible"  # reserved for future "locked_7d" etc.
    apy_min: float                # lowest tier (or single rate if untiered)
    apy_max: float                # highest tier (== apy_min if untiered)
    tier_note: str | None = None  # e.g. "0-500: 8%; 500+: 4.25%"
    raw_json: str | None = None   # response fragment for debugging (stored, not surfaced by API)
    updated_at: datetime

class VenueRateSnapshot(BaseModel):
    venue: str
    rates: list[CexEarnRate]
    errors: list[str] = []

class CexVenue(BaseModel):
    name: str
    display_name: str
    enabled: bool = True
    assets: list[str] = ["USDT", "USDC"]
    notes: str | None = None
```

### ORM tables — `src/stake_watch/storage/tables.py`

Match existing style (`Base = DeclarativeBase`, `Mapped[...]`, `__table_args__ = (Index(...),)`, `Base.metadata.create_all` picks them up):

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
```

Append-only for `cex_earn_rates` (like `protocol_stats`); `cex_venues` is upsert (like `wallets`).

## Collector interfaces

### Base — `src/stake_watch/collectors/cex/base.py`

Duplicate a small retry helper here rather than refactoring `collectors/base.py` (that refactor is a separate concern — see "Deferred refactors"). Helper is < 20 lines, private to `cex/`.

```python
_CEX_MAX_CONCURRENCY = 3
_venue_semaphore = asyncio.Semaphore(_CEX_MAX_CONCURRENCY)  # bounds thundering herd as venues grow

class CexEarnCollector(ABC):
    venue: str
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
        # backoff on 429 / "rate limit" / "too many requests", 3 tries, jittered
        ...
```

### Endpoints — verified prior to spike, may need scraping fallbacks

The reviewer flagged that three of five endpoints in the previous draft were likely wrong or auth-required. **The first implementation step is a "endpoint spike" PR** that verifies each venue with a real network call, updates URLs, and picks a fallback strategy where public JSON isn't available.

Initial expected shape (subject to spike):

| Venue   | Likely reachable via public HTTP? | Notes                                                                                                          |
|---------|-----------------------------------|----------------------------------------------------------------------------------------------------------------|
| Binance | Risky (`bapi/*` is web-internal, often Cloudflare + geo)  | Public `sapi/v1/simple-earn/flexible/list` requires API key. Expect scraping via `curl_cffi` or HTML fallback. |
| OKX     | Yes (`/api/v5/finance/savings/lending-rate-summary`)      | Documented public path.                                                                                        |
| Bybit   | Risky (`/v5/earn/product` may require auth)               | If so: scrape https://www.bybit.com/en/earn/ product page.                                                     |
| Gate    | Risky (correct host is `api.gateio.ws`, not `gateapi.io`) | Spike to verify actual v4 uni-loan or Simple Earn endpoint.                                                    |
| Bitget  | Likely (`/api/v2/earn/savings/product`)                   | Documented public path.                                                                                        |

**Implementation contract per venue file:** URL + headers + parse rules kept as module-level constants; on any upstream schema change only that one file changes. If a venue proves un-reachable after a reasonable spike, it ships with `enabled=false` in seed and a `notes` explaining why — everything else keeps working.

### Registry — `src/stake_watch/collectors/cex/registry.py`

```python
def build_cex_collector(venue: CexVenue) -> CexEarnCollector | None:
    match venue.name:
        case "binance": return BinanceEarnCollector(venue.assets)
        case "okx":     return OkxEarnCollector(venue.assets)
        case "bybit":   return BybitEarnCollector(venue.assets)
        case "gate":    return GateEarnCollector(venue.assets)
        case "bitget":  return BitgetEarnCollector(venue.assets)
        case _:         return None
```

## Scheduler

`scheduler/runner.py`:

- Add `cex_rates_interval: int = 1800` to `ScheduledRunner.__init__` (matches the existing kwarg style used by every other interval).
- Add `_refresh_cex_rates()` coroutine — pattern mirrors `_refresh_dex_liquidity`.
- In `start()`, `if self.cex_rates_interval > 0 and self.storage: add_job(..., next_run_time=datetime.now(timezone.utc))` — this uses APScheduler's `next_run_time` to fire once immediately then on the interval, avoiding a 30-min blank `/cex` page on first launch (the reviewer flagged this).

```python
async def _refresh_cex_rates(self):
    venues = await self.config_store.list_enabled_cex_venues()
    pairs = [(v, c) for v in venues if (c := build_cex_collector(v))]
    snaps = await asyncio.gather(*(c.collect() for _, c in pairs))
    for snap in snaps:
        if snap.rates:
            await self.storage.insert_cex_rates(snap.rates)
        for err in snap.errors:
            logger.warning("cex[%s]: %s", snap.venue, err)
```

Note: single-pass `build_cex_collector(v)` via walrus so `__init__` runs only once per venue.

`main.py`:

```python
cex_refresh_interval = await config_store.get_setting("cex.refresh_interval") or 1800
# ... in ScheduledRunner(...) call:
cex_rates_interval=cex_refresh_interval,
```

`config/seed.yaml` (loaded once by `ConfigStore.import_seed_if_empty`):

```yaml
settings:            # existing block, add key:
  cex.refresh_interval: 1800
```

The `IntervalConfig` Pydantic class is not extended — the CEX interval flows through `get_setting` like other user-tunable intervals (`stablecoin.report_interval`, `protocols.refresh_interval`), not through the seed-only `IntervalConfig` shape.

## FastAPI

New router `src/stake_watch/api/routes/cex.py`, registered in `api/app.py`:

```python
from stake_watch.api.routes import cex
...
app.include_router(cex.router, prefix="/api/cex", tags=["cex"])
```

Endpoints:

| Method | Path                        | Purpose                                                                    |
|--------|-----------------------------|----------------------------------------------------------------------------|
| GET    | `/api/cex/venues`           | list all venues (name, display_name, enabled, assets, notes)               |
| PATCH  | `/api/cex/venues/{name}`    | toggle `enabled` and/or update `assets` (UI-driven)                        |
| GET    | `/api/cex/rates/latest`     | one row per `(venue, asset, product_type)`, latest by `updated_at`         |
| GET    | `/api/cex/rates/history`    | `?venue=&asset=&since=&limit=` — provisioned for future charts             |

Response schema `CexRateOut { venue, venue_display, asset, product_type, apy_min, apy_max, tier_note, updated_at }`. `raw_json` is stored but never returned by the API.

## Seed / migration

Extend `ConfigStore.import_seed_if_empty` so it seeds `cex_venues` independently of `protocol_configs` — this fixes the upgrade path (existing installs with protocols but no CEX venues will still get seeded).

```python
async def import_seed_if_empty(self, seed_path: str = "config/seed.yaml"):
    ...
    # existing block: protocols
    existing = await self.list_protocols()
    if not existing:
        ... # existing seed

    # new block: cex venues, gated separately
    existing_cex = await self.list_cex_venues()
    if not existing_cex:
        for v in seed.get("cex_venues", []):
            await self.upsert_cex_venue(CexVenue(**v))
```

`config/seed.yaml` gains:

```yaml
cex_venues:
  - { name: binance, display_name: Binance, enabled: true, assets: [USDT, USDC] }
  - { name: okx,     display_name: OKX,     enabled: true, assets: [USDT, USDC] }
  - { name: bybit,   display_name: Bybit,   enabled: true, assets: [USDT, USDC] }
  - { name: gate,    display_name: Gate,    enabled: true, assets: [USDT, USDC] }
  - { name: bitget,  display_name: Bitget,  enabled: true, assets: [USDT, USDC] }
```

## Frontend

- `frontend/src/App.tsx` — add `<Route path="/cex" element={<Cex />} />` and a `CEX` link alongside the existing `Protocols` / `Settings` links (whatever pattern is in that file).
- `frontend/src/pages/Cex.tsx` — mirrors `Protocols.tsx` style:
  - Sortable table: Venue · Asset · Flexible APY (renders `apy_min` if `apy_min == apy_max`, else `apy_min%–apy_max%`) · Tiers (hover shows `tier_note`) · Updated
  - Default sort: `apy_max` desc.
  - Subheader: "Refreshed N min ago" from oldest `updated_at`.
  - Collapsible **Manage venues** below the table: checkboxes for `enabled`, asset multi-select; `PATCH /api/cex/venues/{name}` on change.
- `frontend/src/api/` — add a small typed client for the four endpoints, matching existing `api/protocols.ts` style.

No charts in this iteration.

## Testing

Match existing pytest + pytest-asyncio conventions. Target ≥ 90% coverage on new code (all IO is mockable).

- `tests/cex/test_<venue>_collector.py` — one per venue. Load real response fragment from `tests/cex/fixtures/<venue>_earn.json`, mock `httpx.AsyncClient`, assert:
  - USDT and USDC rows produced
  - `apy_min` and `apy_max` correct for tiered and untiered cases
  - `tier_note` contains full breakdown
- `tests/cex/test_registry.py` — every venue name resolves; unknown returns None.
- `tests/cex/test_base_retry.py` — 429 triggers backoff/retry; 500 falls into `errors`, empty rates.
- `tests/storage/test_cex_rates.py` — insert, latest-per-venue-asset query (only most-recent row per key returned), history filter by venue/asset/since/limit.
- `tests/api/test_cex_endpoints.py` — venues list & PATCH, rates latest, rates history — against in-memory sqlite.
- `tests/scheduler/test_cex_job.py` — mock collectors, verify all enabled venues run concurrently and one failure doesn't drop the others; verify `_refresh_cex_rates` writes only non-empty snapshots.

Overall project coverage stays at 80%+; the 392 existing tests remain untouched.

## Deferred refactors

Called out here to prevent scope creep:

- **Shared retry helper.** `_with_rate_limit_retry` in `collectors/base.py` and the private `_with_retry` in `cex/base.py` are duplicative. Extracting to `stake_watch/utils/retry.py` is a legit follow-up but is a cross-cutting change touching a load-bearing file with 392 tests. Deferred.

## Risks / open questions

- **Endpoint availability is the #1 risk.** Public CEX Earn endpoints rot, geo-block, and rotate. Mitigated by (a) doing a real spike PR before wiring the rest, (b) per-venue file isolation, (c) `enabled=false` seed values for venues that need HTML scraping until we ship it. The other four venues keep working even if one venue is completely broken.
- **Cloudflare walls.** If plain `httpx` gets 403 / JS challenge, that venue needs `curl_cffi` (browser TLS fingerprint) or scraping. Deferred until seen; each venue is a self-contained file so the swap is local.
- **Rate semantics.** Storing min+max plus `tier_note` gives the UI enough to render "6.0%–8.0%" without losing information. A future "APY at $10k notional" refinement would add a `notional` column on `CexVenue` and adjust parsers — small change.
- **Positions later.** If we ever add account tracking, `CexEarnCollector` gains a `collect_positions(api_key)` method and a `cex_positions` table; the read/write path stays isolated from the DeFi position pipeline.

## Implementation order (for the plan)

1. **Endpoint spike PR** — probe all five venues, capture real response fragments to `tests/cex/fixtures/`, update the endpoint URLs and per-venue parse rules in this spec (or subsequent plan doc).
2. Models + tables + storage methods + seed extension.
3. Collector base class + retry helper + registry + per-venue collectors (in the order verified in step 1).
4. Scheduler job + `main.py` wiring + `next_run_time=now` for immediate first run.
5. FastAPI router + `api/app.py` registration.
6. Frontend page + nav wiring.
7. Full test suite green + coverage ≥ 90% on new code.