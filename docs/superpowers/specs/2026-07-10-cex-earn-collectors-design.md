# CEX Earn Collectors — Design Spec

**Date:** 2026-07-10
**Status:** Draft (pending review)
**Scope:** Add centralized-exchange USDT/USDC flexible-earn APY collection alongside the existing DeFi protocol monitoring.

## Goal

Show the current USDT/USDC "Simple Earn" / "Flexible Savings" rates from the top CEXes (Binance, OKX, Bybit, Gate, Bitget) in a dedicated `/cex` tab, so the user can compare CEX yields against the DeFi protocols already tracked. Public endpoints only — no API keys, no account-balance tracking, no Telegram alerts.

## Non-goals

- Positions (no account tracking in this iteration).
- Fixed-term / locked / structured / launchpool products (flexible only).
- Risk scoring, safety_rank, or depeg/APY-change alerts on CEX rates.
- Historical charts in the UI (endpoint is provisioned; charting deferred).

## Design decisions

- **Parallel subsystem, not shoehorned into `protocols`.** CEX venues have no chain, no TVL, no pool address, no utilization — treating them as first-class `ProtocolEntry` rows pollutes DeFi field semantics. Instead, mirror the pattern already used by `src/stake_watch/stablecoin/`: a self-contained folder with its own models, storage, API, and page.
- **Lowest tier APY only.** Most CEX flexible products stack tiers ("0–500 USDT: 8%, 500+: 4.25%"). We record the lowest tier (conservative, matches what a non-trivial deposit would actually earn) plus the full tier breakdown as a display-only `tier_note` string.
- **Independent refresh interval.** Rates change slowly and we don't want a fast DeFi cadence to pound five CEX APIs. Default `cex_rates = 1800s` (30 min), user-editable from Settings UI.
- **Failures are silent to Telegram.** Per-venue errors go to logs + a stored `errors` list on the snapshot; no alert path.
- **No new chains.** The `Chain` enum is not extended. CEX venues live in a separate `cex_venues` table, not in the `protocols` table.

## Architecture

```
src/stake_watch/
  cex/                        # NEW
    __init__.py
    base.py                   # CexEarnCollector ABC + module-level concurrency semaphore
    binance.py                # one file per venue
    okx.py
    bybit.py
    gate.py
    bitget.py
    registry.py               # venue name -> collector class
  models/
    cex.py                    # NEW: CexEarnRate, VenueRateSnapshot, CexVenue
  storage/
    cex_rates.py              # NEW: cex_earn_rates + cex_venues CRUD
  api/
    cex.py                    # NEW: /api/cex/*
  scheduler/
    (add refresh_cex_rates job, own interval)
frontend/src/pages/Cex.tsx    # NEW: /cex tab
config/seed.yaml              # add cex_venues block
tests/cex/                    # NEW: collector unit tests + fixtures
```

### Data flow

```
scheduler tick (every cex_rates interval)
  -> storage.list_enabled_cex_venues()
  -> for each venue in parallel (bounded by module-level Semaphore(5)):
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
    apy: Decimal                  # lowest tier, decimal form (0.0425 = 4.25%)
    tier_note: str | None = None  # e.g. "0-500: 8%; 500+: 4.25% (using lowest)"
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

### SQLite tables

**`cex_earn_rates`** — append-only snapshots (same pattern as `protocol_stats`):

| column        | type       | notes                                        |
|---------------|------------|----------------------------------------------|
| id            | INTEGER PK | auto                                         |
| venue         | TEXT       | index                                        |
| asset         | TEXT       | index                                        |
| product_type  | TEXT       | default `"flexible"`                         |
| apy           | REAL       | 0.0425 form                                  |
| tier_note     | TEXT NULL  | display-only breakdown                       |
| raw_json      | TEXT NULL  | raw response fragment for post-hoc debugging |
| updated_at    | DATETIME   | index                                        |

Composite index `(venue, asset, product_type, updated_at DESC)` so "latest per venue×asset" is a fast lookup.

**`cex_venues`** — venue registry (edited from UI):

| column       | type    | notes                                     |
|--------------|---------|-------------------------------------------|
| name         | TEXT PK | binance / okx / bybit / gate / bitget     |
| display_name | TEXT    | UI label                                  |
| enabled      | BOOL    | default true                              |
| assets       | JSON    | `["USDT","USDC"]`                         |
| notes        | TEXT    | free-form                                 |

Both tables created via `CREATE TABLE IF NOT EXISTS` at startup, matching existing style (no alembic in this project).

## Collector interfaces

### Base — `src/stake_watch/cex/base.py`

```python
_venue_semaphore = asyncio.Semaphore(5)

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
```

`_with_retry` reuses the 429-aware backoff pattern from `collectors/base.py` (extract to `stake_watch/utils/retry.py` so both collector families share it).

### Endpoints (public, no auth)

| Venue   | Endpoint                                                                                                                     | Parse rule                                                                                        |
|---------|------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------|
| Binance | `POST https://www.binance.com/bapi/earn/v2/friendly/finance-earn/simple/all`                                                 | filter `productType == "FLEXIBLE"` & `asset ∈ assets`; `tierAnnualInterestRate[]` → min rate     |
| OKX     | `GET  https://www.okx.com/api/v5/finance/savings/lending-rate-summary?ccy=USDT` (and USDC)                                   | single value from `data[0].estRate`                                                              |
| Bybit   | `GET  https://api.bybit.com/v5/earn/product?category=FlexibleSaving&coin=USDT`                                               | `list[].estimateApr`; take min if tiered                                                          |
| Gate    | `GET  https://api.gateapi.io/api/v4/earn/uni/currencies/USDT`                                                                | `min_rate` (or lowest of `tier` list if present)                                                  |
| Bitget  | `GET  https://api.bitget.com/api/v2/earn/savings/product?filter=available_and_held&coin=USDT`                                | `productList[].apyList[]` where `periodType=="flexible"`; min `currentApy`                        |

Each collector file keeps the URL and JSON field names as module constants so an upstream schema change is a one-line fix.

Spike PR verifies all five endpoints publicly return usable data. If any venue closes anonymous access (or geo-blocks), the fallback in that PR is either scraping the public product page HTML or marking the venue disabled in seed with a note. That fallback lives in the same venue file; no cross-cutting change.

### Registry — `src/stake_watch/cex/registry.py`

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

Add job:

```python
async def refresh_cex_rates():
    venues = await storage.list_enabled_cex_venues()
    snaps = await asyncio.gather(
        *(build_cex_collector(v).collect() for v in venues if build_cex_collector(v)),
        return_exceptions=False,
    )
    for snap in snaps:
        await storage.insert_cex_rates(snap.rates)
        for err in snap.errors:
            logger.warning("cex[%s]: %s", snap.venue, err)
```

Interval config addition:

```python
class IntervalConfig(BaseModel):
    ...
    cex_rates: int = 1800   # 30 minutes
```

Trigger once at startup (like other jobs), then on schedule.

## FastAPI

New router `src/stake_watch/api/cex.py`, all read-only except venue toggles:

| Method | Path                        | Purpose                                                                    |
|--------|-----------------------------|----------------------------------------------------------------------------|
| GET    | `/api/cex/venues`           | list all venues (name, display_name, enabled, assets, notes)               |
| PATCH  | `/api/cex/venues/{name}`    | toggle `enabled` and/or update `assets` (UI-driven)                        |
| GET    | `/api/cex/rates/latest`     | one row per `(venue, asset, product_type)`, latest by `updated_at`          |
| GET    | `/api/cex/rates/history`    | `?venue=&asset=&since=&limit=` — provisioned for future charts             |

Response schema `CexRateOut { venue, venue_display, asset, product_type, apy, tier_note, updated_at }`.

## Frontend `/cex` page

`frontend/src/pages/Cex.tsx`, mirroring `Protocols.tsx` style:

- Top nav gains a "CEX" tab (peer of Dashboard / Protocols / Settings).
- Main body: single sortable table.
  - Columns: Venue · Asset · Flexible APY · Tiers (hover shows `tier_note`) · Updated
  - Default sort: APY desc.
- Small subheader: "Refreshed N min ago" (oldest `updated_at` across the table).
- Collapsible **Manage venues** section below the table: checkboxes for `enabled`, asset multi-select; `PATCH /api/cex/venues/{name}` on change.
- No charts in this iteration.

## Seed / migration

`config/seed.yaml` gains a top-level block:

```yaml
cex_venues:
  - { name: binance, display_name: Binance, enabled: true, assets: [USDT, USDC] }
  - { name: okx,     display_name: OKX,     enabled: true, assets: [USDT, USDC] }
  - { name: bybit,   display_name: Bybit,   enabled: true, assets: [USDT, USDC] }
  - { name: gate,    display_name: Gate,    enabled: true, assets: [USDT, USDC] }
  - { name: bitget,  display_name: Bitget,  enabled: true, assets: [USDT, USDC] }
```

At startup, `storage.ensure_cex_venues_seeded(seed)` inserts these rows only if `cex_venues` is empty — subsequent state is DB-owned, matching how `protocols` currently seed.

## Testing

Match existing pytest + pytest-asyncio conventions. Target ≥ 90% coverage on new code (all IO is mockable).

- `tests/cex/test_<venue>_collector.py` — one per venue. Load real response fragment from `tests/cex/fixtures/<venue>_earn.json`, mock `httpx.AsyncClient`, assert:
  - USDT and USDC rows produced
  - `apy` equals the lowest tier
  - `tier_note` contains full breakdown
- `tests/cex/test_registry.py` — every venue name resolves; unknown returns None.
- `tests/cex/test_base_retry.py` — 429 triggers backoff/retry; 500 falls into `errors`, empty rates.
- `tests/storage/test_cex_rates.py` — insert, latest-per-venue-asset query, history filter.
- `tests/api/test_cex_endpoints.py` — venues list & PATCH, rates latest against in-memory sqlite.
- `tests/scheduler/test_cex_job.py` — mock collectors, verify five venues run concurrently and one failure doesn't drop the others.

Overall project coverage stays at 80%+; the 392 existing tests remain untouched.

## Risks / open questions

- **Endpoint stability.** Web/private endpoints (notably Binance's `bapi/…`) may change without notice or geo-block. Mitigation: per-venue URL constant, per-venue fixture-driven test, venue can be disabled from UI. If Binance breaks in production, the other four continue working and the failure is visible in logs (not the product-side app).
- **Cloudflare / bot walls.** If a plain `httpx` request gets a 403 or JS challenge, that venue's collector will need to be scraped from the product page with `curl_cffi` or similar. Deferred; add if we see it in the spike PR.
- **Rate mixing semantics.** "Lowest tier APY" is the conservative interpretation. A tooltip surfaces the full tier list so the user can see the small-balance rate too. If the user later wants "APY at $10k deposit", we add a `notional` field to `CexVenue` and adjust the parser — small change.
- **Positions later.** If we ever add account-balance tracking, `CexEarnCollector` gains a `collect_positions(api_key)` method and a new `cex_positions` table; the read/write path stays isolated from the DeFi position pipeline.