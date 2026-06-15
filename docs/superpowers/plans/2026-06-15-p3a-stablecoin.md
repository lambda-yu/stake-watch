# Stake Watch P3a: Stablecoin Minimum Viable Monitoring

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Monitor USDC and USDT across 7 of the 10 spec items using free APIs (DefiLlama stablecoins, CoinGecko). Items 9-10 already covered by existing protocol collectors.

**Architecture:** New `collectors/stablecoin/` module with price and supply collectors. New stablecoin risk rules. Data stored in existing DB via new StablecoinMetrics model.

**Data Sources:**
- DefiLlama Stablecoins API: per-chain supply, day/week/month changes, price
- CoinGecko Simple Price API: USDC/USDT price + 24h change
- Items 9 (pool utilization) and 10 (withdrawal sim) already exist in protocol collectors

**Depends on:** All previous phases (90 tests)

---

## Feasibility Assessment

| # | Spec Item | Data Source | Feasible in P3a |
|---|---|---|---|
| 1 | Multi-source prices | CoinGecko + DefiLlama | ✅ |
| 2 | DEX pool ratio | On-chain Uniswap/Curve | ❌ Deferred (needs on-chain) |
| 3 | Slippage simulation | DEX router quotes | ❌ Deferred (needs on-chain) |
| 4 | Per-chain total supply | DefiLlama stablecoins | ✅ |
| 5 | 24h mint/burn | DefiLlama day change | ✅ |
| 6 | Exchange net inflow | No free API | ❌ Deferred |
| 7 | Reserve report update | Manual/scrape | ⚠️ Stub (manual override) |
| 8 | Contract events | On-chain events | ❌ Deferred (needs event indexing) |
| 9 | Pool utilization | Existing collectors | ✅ Already done |
| 10 | Withdrawal simulation | Existing Morpho sim | ✅ Already done |

**P3a delivers items 1, 4, 5, 7(stub) + risk rules. Items 2, 3, 6, 8 deferred to P3b.**

---

## Chunk 1: Stablecoin Data Models + Price Collector

### Task S1: Stablecoin models + price collector

**Files:**
- Create: `src/stake_watch/models/stablecoin.py`
- Create: `src/stake_watch/collectors/stablecoin/__init__.py`
- Create: `src/stake_watch/collectors/stablecoin/price.py`
- Create: `src/stake_watch/collectors/stablecoin/supply.py`
- Create: `src/stake_watch/storage/stablecoin_store.py`
- Modify: `src/stake_watch/storage/tables.py` — add StablecoinMetricsRow
- Test files for each

Models:
```python
# src/stake_watch/models/stablecoin.py
class StablecoinPrice(BaseModel):
    token: str                # "USDC" | "USDT"
    price: float              # e.g. 0.9998
    deviation: float          # abs(price - 1.0)
    price_24h_change: float   # percentage
    source: str               # "coingecko" | "defillama"
    updated_at: datetime

class ChainSupply(BaseModel):
    chain: str
    circulating: Decimal
    prev_day: Decimal
    prev_week: Decimal
    change_24h_pct: float     # (current - prev_day) / prev_day

class StablecoinSupply(BaseModel):
    token: str
    total_circulating: Decimal
    chain_breakdown: list[ChainSupply]
    net_change_24h: Decimal
    net_change_24h_pct: float
    net_change_7d_pct: float
    updated_at: datetime

class StablecoinRiskSnapshot(BaseModel):
    token: str
    price: float
    deviation: float
    total_supply: Decimal
    supply_change_24h_pct: float
    supply_change_7d_pct: float
    risk_level: str           # "safe" | "caution" | "danger"
    updated_at: datetime
```

Price collector fetches from CoinGecko + DefiLlama:
```python
# src/stake_watch/collectors/stablecoin/price.py
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
DEFILLAMA_STABLES_URL = "https://stablecoins.llama.fi/stablecoins?includePrices=true"

class StablecoinPriceCollector:
    async def collect_prices(self) -> list[StablecoinPrice]:
        # Fetch from CoinGecko: usd-coin, tether
        # Fetch from DefiLlama stablecoins (price field)
        # Return median price across sources
```

Supply collector fetches from DefiLlama:
```python
# src/stake_watch/collectors/stablecoin/supply.py
class StablecoinSupplyCollector:
    async def collect_supply(self, token: str) -> StablecoinSupply:
        # Fetch from DefiLlama stablecoins API
        # Parse per-chain circulating, prev_day, prev_week
        # Calculate 24h and 7d net changes
```

---

## Chunk 2: Stablecoin Risk Rules + Integration

### Task S2: Stablecoin-specific risk rules

New rules:
- **DepegRule**: deviation > 0.3%+10min → caution, > 0.5%+5min → warning, > 1% → critical
- **SupplyChangeRule**: net redemption > 3%/day → warning, > 5% → high risk
- **StablecoinHardTriggerRule**: price < $0.98 → immediate critical

### Task S3: Stablecoin scheduled collection + API

- Add stablecoin collection to scheduler (1-min price, 10-min supply)
- Add `/api/stablecoins` endpoint returning latest risk snapshot
- Add stablecoin metrics persistence in DB

---

## Summary

| Task | What it builds |
|---|---|
| S1 | Models + price collector (CoinGecko/DefiLlama) + supply collector + DB storage |
| S2 | Depeg rule, supply change rule, hard trigger rule |
| S3 | Scheduler integration + API endpoint + frontend display |
