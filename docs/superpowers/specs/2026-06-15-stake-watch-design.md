# Stake Watch — Design Spec

**Date:** 2026-06-15
**Status:** Draft
**Type:** Personal tool — cross-chain staking yield monitoring + risk alerting platform

---

## 1. Overview

Stake Watch is a personal tool for monitoring staking/lending yields and risks across multiple blockchains, with dedicated USDC/USDT stablecoin risk assessment. It collects on-chain data from DeFi protocols, evaluates risk through configurable rules, and pushes alerts via Telegram.

### Goals

- Monitor staking and lending positions across Solana, Ethereum, BSC, and Base
- Track yields (APY) and compare across protocols
- Detect and alert on liquidation risk, stablecoin depeg, protocol-level events, and yield changes
- Provide an 8-layer stablecoin risk monitoring framework for USDC and USDT
- Push alerts to Telegram with severity levels and cooldown deduplication

### Non-Goals

- Not a trading bot or auto-rebalancer
- Not a multi-user SaaS product
- No mobile app

---

## 2. Architecture

### Tech Stack

| Component | Choice | Rationale |
|---|---|---|
| Runtime | Python 3.12+ | User preference, strong ecosystem |
| Async | asyncio + httpx | High-concurrency collection |
| Package manager | uv | Fast dependency management |
| Solana SDK | solders + solana-py | Native RPC interaction |
| EVM SDK | web3.py | Standard choice |
| Database | SQLite + SQLAlchemy | Lightweight for personal use |
| Scheduler | APScheduler | Mature Python scheduling |
| Telegram | python-telegram-bot | Official recommended library |
| API | FastAPI + uvicorn | Config management + data API |
| Frontend | React + TypeScript + Vite | SPA for config and monitoring |
| Frontend UI | Tailwind CSS + shadcn/ui | Rapid, polished UI components |
| Config storage | DB-stored, managed via REST API | All config from frontend, no YAML editing |
| Auxiliary APIs | DefiLlama, CoinGecko | Free, no API key required |
| Testing | pytest + pytest-asyncio + Vitest | Backend + frontend tests |

### Project Structure

```
stake-watch/
├── pyproject.toml
├── .env                            # Bootstrap only: DB path, server port
├── config/
│   └── seed.yaml                   # First-time DB initialization seed data
├── src/
│   └── stake_watch/
│       ├── __init__.py
│       ├── main.py                 # Entry point: FastAPI + scheduler startup
│       ├── models/
│       │   ├── position.py         # Position: chain, protocol, asset, amount, APY, LTV
│       │   ├── protocol.py         # Protocol metadata: TVL, rates, status
│       │   ├── alert.py            # Alert event model
│       │   └── stablecoin.py       # Stablecoin metrics and risk score
│       ├── api/
│       │   ├── __init__.py
│       │   ├── app.py              # FastAPI application factory
│       │   ├── deps.py             # Dependency injection (Storage, ConfigStore)
│       │   └── routes/
│       │       ├── config.py       # Wallets, RPC, intervals, risk thresholds CRUD
│       │       ├── protocols.py    # Protocol CRUD + enable/disable
│       │       └── status.py       # System health, collector status
│       ├── collectors/
│       │   ├── base.py             # BaseCollector abstract base class
│       │   ├── solana/
│       │   │   ├── jupiter_lend.py
│       │   │   ├── kamino.py
│       │   │   └── liquid_staking.py
│       │   ├── ethereum/
│       │   │   ├── aave.py
│       │   │   ├── compound.py
│       │   │   ├── fluid.py
│       │   │   ├── sky_susds.py
│       │   │   ├── lido.py
│       │   │   └── eigenlayer.py
│       │   ├── bsc/
│       │   │   └── venus.py
│       │   ├── base_chain/
│       │   │   └── aave_base.py
│       │   ├── morpho/                    # Shared across Base + Ethereum
│       │   │   ├── base_morpho.py         # Shared vault/market reading
│       │   │   ├── models.py              # Morpho-specific data models
│       │   │   ├── vault.py               # Vault: shares, allocation, queue, version
│       │   │   ├── market.py              # Per-market: utilization, liquidity, LLTV
│       │   │   ├── oracle.py              # Oracle health & cross-validation
│       │   │   ├── bad_debt.py            # Bad debt & stress testing
│       │   │   ├── governance.py          # Curator/owner/allocator events
│       │   │   ├── withdrawal_sim.py      # 10%/50%/100% withdrawal simulation
│       │   │   ├── adapters.py            # V2 adapter monitoring
│       │   │   ├── chain_base.py          # Base-specific: addresses, sequencer
│       │   │   └── chain_ethereum.py      # Ethereum-specific: addresses
│       │   └── stablecoin/
│       │       ├── price.py              # Layer 1: Multi-source price depeg
│       │       ├── dex_liquidity.py      # Layer 2: DEX pool skew + slippage sim
│       │       ├── supply.py             # Layer 3: On-chain supply & redemption
│       │       ├── reserves.py           # Layer 4: Issuer reserve monitoring
│       │       ├── blacklist.py          # Layer 5: Freeze & blacklist events
│       │       ├── cross_chain.py        # Layer 6: Cross-chain version verify
│       │       ├── cex_spread.py         # Layer 7: CEX price spread
│       │       └── protocol_exposure.py  # Layer 8: Deposit protocol exposure
│       ├── risk/
│       │   ├── engine.py           # Rule evaluation engine
│       │   ├── stablecoin_scorer.py # 7-dimension weighted scoring
│       │   ├── morpho_scorer.py    # Morpho vault composite risk scoring
│       │   └── rules/
│       │       ├── base.py
│       │       ├── liquidation.py
│       │       ├── depeg.py
│       │       ├── protocol_event.py
│       │       ├── yield_change.py
│       │       ├── stablecoin.py
│       │       └── morpho.py       # Morpho-specific risk rules
│       ├── alerts/
│       │   ├── base.py           # BaseNotifier ABC
│       │   └── telegram.py       # Telegram Bot notifier
│       ├── storage/
│       │   ├── db.py             # SQLite + SQLAlchemy engine
│       │   ├── tables.py         # All table definitions (data + config)
│       │   └── config_store.py   # Config-specific CRUD (wallets, RPC, protocols, settings)
│       └── scheduler/
│           └── runner.py         # APScheduler driver
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── App.tsx
│       ├── main.tsx
│       ├── api/                   # API client
│       │   └── client.ts
│       ├── pages/
│       │   ├── Dashboard.tsx      # Overview: protocol status, collector health
│       │   ├── Settings.tsx       # Wallets, RPC, intervals, thresholds, Telegram
│       │   ├── Protocols.tsx      # Protocol list + add/edit/toggle
│       │   └── Alerts.tsx         # Alert history (P2)
│       └── components/
│           ├── Layout.tsx
│           ├── WalletForm.tsx
│           ├── ProtocolCard.tsx
│           └── ThresholdEditor.tsx
├── tests/
├── docs/
└── scripts/
```

### Data Flow

```
Scheduler (APScheduler cron)
    │
    ▼
Collectors (per-protocol, async batch via asyncio.gather)
    │
    ├──▶ Storage (SQLite) ──▶ Risk Engine ──▶ Telegram Bot
    │                              │
    │                     Rule Evaluator (thresholds)
    │                     Stablecoin Scorer (8-layer)
    │
    └── Single collector failure does not block others
```

---

## 3. Core Abstractions

### BaseCollector

```python
class BaseCollector(ABC):
    chain: Chain           # solana | ethereum | bsc | base
    protocol: str          # "jupiter_lend" | "aave" | ...

    @abstractmethod
    async def collect_positions(self, wallet: str) -> list[Position]: ...

    @abstractmethod
    async def collect_protocol_stats(self) -> ProtocolStats: ...

    async def collect(self, wallet: str) -> CollectResult:
        """Unified entry: positions + protocol data"""
```

### Data Models

```python
class Position(BaseModel):
    chain: Chain
    protocol: str
    wallet: str
    asset: str
    position_type: PositionType   # supply | borrow | stake | lp | vault
    amount: Decimal
    value_usd: Decimal
    apy: float
    ltv: float | None
    health_factor: float | None
    vault_version: str | None     # For Morpho: "v1.0" | "v1.1" | "v2"
    updated_at: datetime

class ProtocolStats(BaseModel):
    chain: Chain
    protocol: str
    tvl_usd: Decimal
    pools: list[PoolStats]
    updated_at: datetime
```

### Scheduling

| Data type | Interval |
|---|---|
| Stablecoin prices + CEX spread | 1 min |
| Positions | 5 min |
| DEX liquidity + blacklist events | 5 min |
| Protocol stats (TVL/rates) | 15 min |
| On-chain supply | 10 min |
| Reserve reports | 6 hours |
| Cross-chain version verify | Startup + 24 hours |

### RPC Data Sources

- Solana: Helius (paid, primary) + public RPC fallback
- Ethereum: Alchemy or Infura (paid, primary) + public RPC fallback
- Base: Alchemy Base (paid, primary) + public RPC fallback
- BSC: Public RPC (lower polling frequency acceptable)
- Auxiliary: DefiLlama API (TVL/APY), CoinGecko (prices)
- All endpoints configured in `settings.yaml` with auto-failover
- **Paid RPC required for ETH and Base** due to sub-minute polling cadence; public endpoints rate-limit too aggressively

---

## 4. Risk Engine

### Rule Types

```python
class RuleType(Enum):
    LIQUIDATION = "liquidation"
    DEPEG = "depeg"
    PROTOCOL_EVENT = "protocol_event"
    YIELD_CHANGE = "yield_change"
```

### Rule Interface

```python
class BaseRule(ABC):
    rule_type: RuleType
    severity: Severity           # critical | warning | info
    cooldown: timedelta

    @abstractmethod
    def evaluate(self, context: RuleContext) -> Alert | None: ...
```

### Default Thresholds

| Rule | Default Threshold | Severity |
|---|---|---|
| LTV near liquidation | health_factor < 1.3 warning, < 1.1 critical | warning/critical |
| Stablecoin depeg | >0.5% warning, >2% critical | warning/critical |
| USDC/USDT supply change | 24h change >5% | warning |
| Protocol TVL crash | >15% drop in 1h | critical |
| Contract upgrade | Upgrade authority call detected | info |
| APY swing | >30% relative change in 24h | info |
| Collector failure | 3 consecutive failures | warning |

### Alert Deduplication & Cooldown

- Same rule + same position: no repeat within cooldown period
- Critical: 15 min cooldown
- Warning: 1 hour cooldown
- Info: 6 hour cooldown
- "Recovered" notification sent once when status returns to normal

---

## 5. Stablecoin Risk Module — 8-Layer Architecture

### USDC vs USDT Risk Differences

| Aspect | USDC | USDT |
|---|---|---|
| Issuer | Circle | Tether |
| Reserve transparency | Monthly attestation, higher transparency | Periodic reports, more diverse assets |
| Primary reserves | Cash, short-term US Treasuries | US Treasuries, gold, Bitcoin, other |
| Regulatory | Stronger US regulatory ties | Global usage, complex issuance structure |
| On-chain liquidity | Strong on EVM, Solana, Base | Strong on Ethereum, Tron, CEX |
| Freeze capability | Yes | Yes |

### Layer 1: Multi-Source Price Depeg Detection

**Data sources:** Chainlink, CoinGecko, Coinbase, Binance, Kraken, Uniswap/Curve, Jupiter (Solana)

**Detection logic:**
- reference_price = median(all sources)
- deviation = abs(reference_price - 1.0)
- Dual-dimension: deviation magnitude + sustained duration

| Deviation | Duration | Status |
|---|---|---|
| >1% | Immediate | CRITICAL |
| >0.5% | 5 min sustained | WARNING |
| >0.3% | 10 min sustained | CAUTION |
| <0.2% | — | NORMAL |

**Action thresholds:**

| Price Range | Status | Suggested Action |
|---|---|---|
| 0.998–1.002 | Normal | No action |
| 0.995–0.998 | Watch | Increase sampling frequency |
| 0.990–0.995 | Warning | Pause new deposits |
| 0.980–0.990 | High risk | Start reducing exposure |
| <0.980 | Critical | Prioritize exit |

### Layer 2: DEX Liquidity & Pool Skew

**Monitored pools:** USDC/USDT, USDC/DAI, USDT/DAI, USDC/USDS

**Metrics:**
- Pool reserve ratio (normal: ~50/50)
- Simulated sell slippage at $100K, $1M, $5M
- 24h net sell volume
- LP liquidity changes

**Alerts:**
- Single-side ratio >65%: Watch
- >75%: Warning
- >85%: Critical
- $1M slippage >0.5%: Warning (even if price near $1.00)

### Layer 3: On-Chain Supply & Redemption Pressure

**Monitored chains:** Ethereum, Base, Arbitrum, Optimism, Solana, Tron

**Metrics per chain:**
- total_supply, 24h minted, 24h burned, 7d minted, 7d burned
- bridge inflow/outflow, exchange inflow/outflow

**Key calculation:**
- Net redemption rate = 24h net burn / total supply

| Net Redemption | Risk Level |
|---|---|
| <1%/day | Normal |
| 1–3%/day | Watch |
| 3–5%/day | Warning |
| >5%/day | High risk |

**Context required:** Large burns may be cross-chain migration. Must cross-reference issuer announcements, other chain supply, exchange flows, and price.

### Layer 4: Issuer Reserve Monitoring

**USDC (Circle):**
- Circulating supply vs reserve assets
- Coverage ratio = reserve fair value / circulating supply
- Reserve composition (cash, short-term Treasuries)
- Custodian bank changes
- Report publication delays (>7d yellow, >14d orange, unexplained delay red)
- Redemption functionality status

**USDT (Tether):**
- Coverage ratio + reserve breakdown:
  - Cash & equivalents, US Treasuries, gold, Bitcoin, secured loans, other
- Key ratios: high-liquidity reserves / total USDT, risk assets / equity buffer
- Excess reserves adequacy to cover volatile asset drawdowns

**Hard trigger:** Coverage ratio <100% → immediate CRITICAL

### Layer 5: Freeze & Blacklist

**Per-wallet monitoring:**
- USDC: `isBlacklisted(address)` via eth_call
- USDT: `isBlackListed(address)` via eth_call
- Contract functions vary by chain — use chain-specific ABI

**Global event monitoring:**
- Blacklisted / UnBlacklisted events
- Pause / Unpause
- OwnershipTransferred
- Upgraded (proxy implementation change)

### Layer 6: Cross-Chain Version Verification

**Distinguish native vs bridged:**
- Native USDC vs USDbC (Base bridged, extra bridge risk)
- USDC.e, Bridged USDT, Axelar/Wormhole variants

**Verification fields:** chain_id, contract_address, issuer, bridge, decimals, proxy implementation

**Whitelist registry in `config/stablecoins.yaml`:**

```yaml
usdc:
  ethereum:
    address: "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    type: native
  base:
    address: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    type: native
  base_bridged:
    address: "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA"
    type: bridged
    risk_premium: 10
  solana:
    address: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    type: native
usdt:
  ethereum:
    address: "0xdAC17F958D2ee523a2206206994597C13D831ec7"
    type: native
  tron:
    address: "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    type: native
```

**Any same-symbol token not in whitelist → flag red.**

### Layer 7: CEX Price Spread

**Monitor:** USDC/USD, USDC/USDT, USDT/USD across major exchanges

**Calculation:** spread = max(price) - min(price)

| Spread | Status |
|---|---|
| >0.2% | Watch |
| >0.5% | Warning |
| >1% | High risk |

**Special attention:** If DEX prices normal but fiat off-ramps abnormal (Coinbase, Kraken, Bitstamp), may indicate redemption or banking channel issues.

### Layer 8: Deposit Protocol Exposure

**Per-protocol metrics:**
- Total deposits, total borrows, utilization rate
- Available liquidity, collateral distribution
- Liquidation debt, bad debt, oracle status
- Admin permissions, upgrade events

**Key calculations:**

```
Protocol stablecoin exposure / total on-chain supply of that stablecoin

Your withdrawable liquidity = vault idle assets + underlying market available liquidity
```

**Withdrawal simulation (every 5 min):**
- Simulate withdraw 10%, 50%, 100% of position
- Alert if liquidity_ratio < 1.0

### Composite Risk Scoring

**7-dimension weighted model (0–100, higher = more risky):**

Layer 8 (Protocol Exposure) is excluded from the composite score — it feeds per-position alerts and hard triggers (withdrawal simulation failure) rather than the aggregate stablecoin risk score.

| Dimension | Weight | Source Layer |
|---|---|---|
| Depeg risk | 25% | Layer 1 |
| DEX liquidity risk | 15% | Layer 2 |
| Redemption pressure | 15% | Layer 3 |
| Reserve risk | 20% | Layer 4 |
| Issuer & regulatory risk | 10% | Layer 5 |
| On-chain contract risk | 10% | Layers 5+6 |
| Cross-chain version risk | 5% | Layer 6 |

**Risk levels:**

| Score | Level |
|---|---|
| 0–20 | Green (safe) |
| 20–35 | Yellow (watch) |
| 35–50 | Orange (caution) |
| 50–70 | Red (danger) |
| 70–100 | Critical |

**8 hard triggers (bypass scoring, immediate CRITICAL):**

1. Price < $0.98
2. Issuer halts redemptions
3. Reserve coverage < 100%
4. Stablecoin contract paused
5. Your address blacklisted
6. Unknown contract upgrade
7. Multiple CEX suspend deposits/withdrawals
8. $1M DEX slippage >2%

---

## 6. Protocol Deep Monitoring — Morpho on Base (10-Layer)

Morpho requires deeper monitoring than typical lending protocols because of its unique architecture: permissionless market creation, Vault-based fund allocation by curators, and oracle-agnostic design. This section applies to any Morpho deployment (Base, Ethereum, etc.) but is designed with Base as the primary target.

### Morpho Architecture Context

Two deposit modes with different risk profiles:
- **Direct Market deposit**: You choose a specific market (e.g., WETH/USDC at 86% LLTV)
- **Vault deposit**: Curator allocates your funds across multiple markets automatically

Vault deposit is more common but adds curator trust risk. All monitoring must drill down to individual underlying markets.

### Safety Assessment (USDC Supply-Only)

| Scenario | Safety Rating |
|---|---|
| Quality curator, mainstream collateral, conservative LLTV | ~8/10 |
| Direct single WETH/USDC or cbBTC/USDC market | ~7-8/10 |
| Complex Vault with exotic collateral or high LLTV | ~5-6/10 |
| Chasing highest APY without checking Vault internals | ~4-5/10 |

### Morpho vs Jupiter Lend Comparison

| Aspect | Morpho Base | Jupiter Lend |
|---|---|---|
| Market isolation | Clearer, each market independent | Shared liquidity layer underneath |
| Market creation | Permissionless, anyone can create | Relatively centralized |
| Risk parameters | Immutable after market creation | Some parameters adjustable |
| Vault management risk | Significant, depends on curator | Relatively lower |
| Network risk | Base L2, sequencer & bridge risk | Solana network risk |
| Monitoring difficulty | Easier, EVM events are clear | Slightly more complex |

### Layer M1: Per-Market Fund Allocation

Every Vault distributes funds across multiple markets. Must monitor each individually.

**Data model:**

```python
class MorphoMarketAllocation(BaseModel):
    vault_address: str
    market_id: str           # keccak256(loanToken, collateralToken, oracle, irm, lltv)
    loan_token: str
    collateral_token: str
    oracle: str
    irm: str
    lltv: float
    supply_assets: Decimal
    borrow_assets: Decimal
    liquidity: Decimal
    utilization: float
    allocation_percent: float
    supply_cap: Decimal | None
```

**Key insight:** Same token pair (e.g., WETH/USDC) with different Oracle or LLTV = completely different market with different risks.

### Layer M2: Utilization & Withdrawable Liquidity

```
utilization = totalBorrowAssets / totalSupplyAssets
```

| Utilization | Status |
|---|---|
| <75% | Normal |
| 75-85% | Watch |
| 85-92% | Warning |
| >92% | High risk |
| >97% | Critical |

**Withdrawable liquidity calculation:**

```
direct_available = vault_idle_assets + sum(market_available for each market)
personal_exit_ratio = direct_available / your_deposit
```

Morpho Vault can reallocate via Public Allocator across approved markets, so actual withdrawal capacity may exceed single-market idle liquidity. But monitoring must calculate both.

**Alert:** `personal_exit_ratio < 1.0` → WARNING

### Layer M3: Withdrawal Queue Monitoring

Vault V1 has supply queue and withdrawal queue. Withdrawals are processed in withdrawal queue order.

**Monitor:**
- withdrawQueue composition and order changes
- First-position market available liquidity
- Whether deprecated or high-risk markets appear in queue
- Whether multiple queue markets have utilization >95%

**Red flags:**
- High-liquidity market removed from withdrawal queue
- Exotic market placed at front of queue
- All queue markets above 95% utilization

### Layer M4: LLTV Risk Assessment

LLTV is the liquidation threshold, not the borrower's target LTV.

| LLTV | Risk Assessment |
|---|---|
| ≤77% | Conservative |
| 77-82.5% | Moderate |
| 82.5-86% | Elevated |
| >86% | High risk, requires deep asset liquidity |

For mainstream assets (WETH, cbBTC), 86% is widely used and acceptable. For exotic LSTs, wrapped assets, or yield-bearing tokens, 86% requires extreme caution.

### Layer M5: Bad Debt Monitoring & Stress Testing

Bad debt in Morpho directly impacts lenders in that market.

**Real-time per-borrower calculation:**

```python
class BorrowerRisk(BaseModel):
    collateral_value: Decimal
    debt: Decimal
    ltv: float
    health_factor: float
    liquidatable_debt: Decimal
    potential_bad_debt: Decimal
```

**Stress test scenarios (every 5 min):**

| Collateral Drop | Output |
|---|---|
| -5% | badDebtUsdDown5 |
| -10% | badDebtUsdDown10 |
| -20% | badDebtUsdDown20 |
| -30% | badDebtUsdDown30 |

**Key metric:** `potential_bad_debt / vault_total_assets`

| Bad Debt / Vault Assets | Status |
|---|---|
| <0.1% | Normal |
| 0.1-0.5% | Watch |
| 0.5-1% | Warning |
| >1% | High risk |
| >3% | Critical |

### Layer M6: Vault Version & Loss Realization

Must identify vault version: V1.0, V1.1, or V2.

**Critical difference:**
- **V1.0**: Bad debt immediately reflected in share price — all depositors take proportional loss
- **V1.1**: Bad debt may not immediately reflect in share price — late exiters may bear disproportionate loss

**Monitor:**
- vault_version
- share_price (convertToAssets(1e18))
- lastTotalAssets
- realized_bad_debt vs unrealized_bad_debt
- Large depositor exits before bad debt confirmation

**Alert:** share_price decrease → immediate CRITICAL

### Layer M7: Oracle Risk

Morpho is oracle-agnostic — market creators choose any oracle. Cannot assume safety from Chainlink alone.

**Monitor per-market:**

```python
class OracleHealth(BaseModel):
    oracle_address: str
    oracle_type: str
    base_feed: str
    quote_feed: str
    price: Decimal
    staleness: timedelta
    heartbeat: timedelta
    feed_description: str
```

**Cross-validation against:**
- Chainlink reference feeds
- Uniswap V3 TWAP
- Aerodrome TWAP
- Coinbase / Binance spot

**Alert thresholds:**

| Asset Type | Deviation | Severity |
|---|---|---|
| WETH, cbBTC | >1% | Warning |
| WETH, cbBTC | >2% | High risk |
| Stablecoins | >0.3% | Warning |
| Stablecoins | >1% | High risk |
| Any | Update > heartbeat | Warning |
| Any | price() call reverts | CRITICAL |

**Key insight:** If oracle price() reverts, borrowing, collateral withdrawal, AND liquidation all freeze — bad debt risk escalates rapidly.

### Layer M8: Curator & Vault Governance

Depositing in a Vault means trusting the curator, owner, allocator, and guardian.

**Monitor events:**
- SetCurator, SetGuardian, SetAllocator
- SetFee, SetCap, SubmitCap, AcceptCap
- SubmitMarketRemoval, RevokePendingCap
- SetSupplyQueue, UpdateWithdrawQueue

**Alert thresholds:**

| Event | Severity |
|---|---|
| New market added to Vault | Yellow |
| Single market cap increased >10% of Vault assets | Orange |
| Timelock reduced to 0 | Red |
| Owner/curator changed to unknown EOA | Red |
| Guardian removed | Red |
| Unknown allocator added | Orange |

**Best practice check:** Owner should be multisig, guardian should be separate trusted party.

### Layer M9: Vault V2 Adapter Risk

Vault V2 can deploy funds to non-Morpho protocols via adapters, expanding attack surface.

**Monitor:**
- adapter list, adapter_registry
- adapter bytecode hash (detect changes)
- adapter exposure (amount deployed)
- adapter cap, adapter timelock

**Red line conditions (any = high risk):**
- No trusted Adapter Registry
- Curator can add adapters quickly
- Timelock is zero or very short

A V2 Vault currently deploying only to Morpho Markets can still become high-risk if these conditions exist.

### Layer M10: Base L2 Network Risk

Base-specific risks that affect all protocols on the chain:

**Monitor:**
- Base latest block age
- L1 batch submission delay
- Sequencer uptime (Chainlink sequencer uptime feed)
- L2 to L1 finality gap
- Gas price spikes
- Withdrawal transaction simulation

**Sequencer downtime impact:**
- User transactions may not be submitted
- Liquidations may be delayed
- Fast price drops during downtime → increased bad debt

**Base asset classification:**

| Asset | Additional Risk |
|---|---|
| Native Base USDC | Relatively low |
| USDbC | Bridged asset risk |
| cbBTC | Coinbase custody & redemption risk |
| WETH | Base bridge & L2 risk |
| wstETH / cbETH | LST & issuer risk |
| ERC-4626 yield assets | Share price manipulation, donation attacks, underlying protocol risk |

### Morpho Composite Risk Scoring

**7-dimension weighted model mapping 10 layers to scoring dimensions:**

Layers M1 (Allocation) and M3 (Withdrawal Queue) feed into the "Market utilization & liquidity" dimension. Layer M9 (Adapter) feeds "Vault version & adapter risk".

| Dimension | Weight | Source Layers |
|---|---|---|
| Market utilization & liquidity | 20% | M1, M2, M3 |
| Bad debt & stress test | 20% | M5, M6 |
| Oracle health | 15% | M7 |
| LLTV risk profile | 15% | M4 |
| Curator & governance | 15% | M8 |
| Base L2 network | 10% | M10 |
| Vault version & adapter risk | 5% | M6, M9 |

**11 hard triggers (bypass scoring, immediate CRITICAL):**

1. Share price decrease
2. Confirmed bad debt
3. 10% withdrawal simulation fails
4. Oracle stops updating or severe deviation
5. Unknown collateral market added to Vault
6. Timelock significantly reduced
7. Curator/Owner changed to unknown address
8. Single high-risk market exceeds 20% of Vault
9. All withdrawal queue markets >95% utilization
10. Vault V2 adds unknown adapter
11. USDC depeg (linked to stablecoin module)

### Morpho Minimum Viable Monitoring (8 items for P1)

1. Vault total assets and your shares
2. Per-market fund allocation percentages
3. Per-market utilization and available liquidity
4. 10%, 50%, 100% withdrawal eth_call simulation
5. LLTV, oracle address, and price deviation
6. Near-liquidation positions and potential bad debt
7. Vault cap, queue, curator, allocator change events
8. Base sequencer and RPC status

### Morpho Collection Frequency

| Metric | Frequency |
|---|---|
| Utilization & liquidity | 1 min |
| Oracle prices | 60 sec |
| Withdrawal simulation | 5 min |
| Vault governance events | WebSocket real-time (fallback: 1 min polling) |
| Borrower position risk | 1 min |
| Stress testing | 5 min |
| Base network status | 30 sec |

---

## 7. Telegram Alerts

### Message Format

```
[CRITICAL] Liquidation Risk Alert
━━━━━━━━━━━━━━━━━━━━━━
Chain: Solana | Protocol: Jupiter Lend
Position: USDC borrow
Health Factor: 1.08 (threshold: 1.1)
LTV: 91.2%
━━━━━━━━━━━━━━━━━━━━━━
Action: Add collateral or reduce borrow
```

```
[WARNING] Stablecoin Deviation
━━━━━━━━━━━━━━━━━━━━━━
Asset: USDT
Price: $0.994 (deviation: 0.6%)
24h supply change: -3.2%
DEX pool skew: 72% USDT / 28% USDC
Risk score: 42/100 (Orange)
━━━━━━━━━━━━━━━━━━━━━━
```

### Notifier Interface

```python
class BaseNotifier(ABC):
    @abstractmethod
    async def send(self, alert: Alert) -> bool: ...
```

Only Telegram in V1. BaseNotifier allows future Discord/email additions.

---

## 8. Delivery Phases

| Phase | Scope | Depends on |
|---|---|---|
| **P1a** | Project skeleton + data models + SQLite storage + BaseCollector + DefiLlama collector + scheduler | — |
| **P1b** | FastAPI config API + React frontend skeleton + config management pages (Settings, Protocols) | P1a |
| **P1-morpho** | Morpho 10-layer deep monitoring MVP (8 core metrics) | P1a |
| **P2** | Risk rule engine + Telegram Bot + all alert types + Morpho-specific rules + deduplication/cooldown | P1a |
| **P2-protocols** | Additional protocol collectors: Sky sUSDS, Compound V3, Fluid, Kamino + per-protocol risk rules | P2 |
| **P3a** | Stablecoin minimum viable monitoring (10 core metrics) | P1a |
| **P3b** | Full 8-layer stablecoin module + composite scoring model | P3a |
| **P4** | Data visualization dashboards (protocol overview, yield comparison, risk heatmaps) | P1b |

### P3a Minimum Viable Stablecoin Monitoring (10 items)

1. USDC/USD and USDT/USD multi-source prices
2. USDC/USDT DEX pool ratio
3. $1M and $5M sell slippage simulation
4. Per-chain total supply
5. 24h mint and burn
6. Exchange net inflow
7. Official reserve report update time
8. Contract upgrade, pause, blacklist events
9. Your lending pool utilization and liquidity
10. 10%, 50%, 100% withdrawal simulation

---

## 9. Configuration (DB-Stored, Frontend-Managed)

All user-facing configuration is stored in SQLite and managed through the React frontend via FastAPI REST API. No YAML file editing for runtime settings.

### Config Storage Architecture

```
First startup:
  config/seed.yaml exists + DB config tables empty
    → import seed data into DB
    → seed.yaml stays as reference, never read again at runtime

Normal startup:
  Load all config from DB → build AppSettings → pass to collectors/scheduler

Runtime config change (via frontend):
  User edits in React UI → PUT /api/config/... → update DB
    → scheduler picks up changes on next collection cycle (hot-reload)
```

### Bootstrap Config (.env only)

Only infrastructure-level config lives in `.env` (not user-facing):

```env
# .env — bootstrap config, not managed by frontend
DATABASE_URL=sqlite:///stake_watch.db
API_HOST=0.0.0.0
API_PORT=8000
```

### DB Config Tables

```python
class WalletRow(Base):
    __tablename__ = "wallets"
    id: int (PK, autoincrement)
    chain: str              # "base" | "ethereum" | "solana" | "bsc"
    address: str
    label: str | None       # user-friendly name, e.g. "My Base Wallet"
    created_at: datetime

class RpcEndpointRow(Base):
    __tablename__ = "rpc_endpoints"
    id: int (PK, autoincrement)
    chain: str (unique)
    primary_url: str
    fallback_urls: str      # JSON array of strings
    updated_at: datetime

class ProtocolConfigRow(Base):
    __tablename__ = "protocol_configs"
    id: int (PK, autoincrement)
    name: str (unique)
    chain: str
    collector: str
    enabled: bool = True
    safety_rank: int | None
    safety_score: float | None
    reference_apy: str | None
    primary_risks: str      # JSON array
    vault_address: str | None
    defillama_slug: str | None
    created_at: datetime
    updated_at: datetime

class AppSettingsRow(Base):
    __tablename__ = "app_settings"
    key: str (PK)           # e.g. "intervals.positions", "risk.liquidation_warning"
    value: str              # JSON-encoded value
    updated_at: datetime
```

### REST API Endpoints

```
# Wallet management
GET    /api/config/wallets           → list all wallets
POST   /api/config/wallets           → add wallet {chain, address, label}
PUT    /api/config/wallets/{id}      → update wallet
DELETE /api/config/wallets/{id}      → remove wallet

# RPC endpoint management
GET    /api/config/rpc               → list all RPC configs
PUT    /api/config/rpc/{chain}       → update RPC for chain {primary_url, fallback_urls}

# Polling intervals
GET    /api/config/intervals         → get all intervals
PUT    /api/config/intervals         → update intervals {positions, protocol_stats, ...}

# Risk thresholds
GET    /api/config/risk              → get all risk thresholds
PUT    /api/config/risk              → update thresholds {liquidation_warning, depeg_warning, ...}

# Telegram config
GET    /api/config/telegram          → get telegram config
PUT    /api/config/telegram          → update {bot_token, chat_id}

# Protocol management
GET    /api/protocols                → list all protocols
POST   /api/protocols                → add protocol
PUT    /api/protocols/{id}           → update protocol
PATCH  /api/protocols/{id}/toggle    → toggle enable/disable
DELETE /api/protocols/{id}           → remove protocol

# System status
GET    /api/status                   → system health, uptime, last collection
GET    /api/status/collectors        → per-collector status and error counts
```

### Frontend Pages

| Page | URL | Purpose |
|---|---|---|
| Dashboard | `/` | Protocol status overview, collector health, last collection times |
| Settings | `/settings` | Wallet management, RPC endpoints, intervals, risk thresholds, Telegram |
| Protocols | `/protocols` | Protocol list with enable/disable toggle, add/edit forms |
| Alerts | `/alerts` | Alert history and management (P2) |

### Seed Data (config/seed.yaml)

Used only for first-time DB initialization:

```yaml
# config/seed.yaml — imported into DB on first startup only
wallets: []

rpc:
  base:
    primary: "https://mainnet.base.org"
  ethereum:
    primary: "https://eth.public-rpc.com"
  solana:
    primary: "https://api.mainnet-beta.solana.com"
  bsc:
    primary: "https://bsc-dataseed.binance.org"

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

protocols:
  - name: aave_v3_base
    chain: base
    collector: defillama
    defillama_slug: aave-v3
    safety_rank: 1
    safety_score: 8.8
    enabled: true
  # ... (same protocol list as §11)
```

---

## 10. Key Design Decisions

1. **One collector per protocol file** — all inherit BaseCollector with unified `collect()` interface
2. **Config-driven** — adding a new protocol only requires a collector file + config entry
3. **SQLite first** — sufficient for personal use, painless migration to PostgreSQL later
4. **All collectors run concurrently** via `asyncio.gather`, single failure isolated
5. **Stablecoin risk as 8 independent layers** — each layer has its own collector, can be enabled/disabled independently
6. **Hard triggers override scoring** — critical conditions bypass weighted model for immediate alerts
7. **Whitelist-based stablecoin verification** — prevents confusion between native and bridged versions
8. **Dual-dimension depeg detection** — deviation magnitude + sustained duration, avoids false alarms from single anomalous trades
9. **Morpho gets 10-layer deep monitoring** — unique architecture (permissionless markets, curator-managed Vaults, oracle-agnostic) demands deeper monitoring than pooled lending protocols
10. **Protocol safety ranking as config** — each protocol carries a baseline safety score and primary risk list; risk engine can weight alerts accordingly

---

## 11. Protocol Safety Reference (USDC Supply)

Baseline safety ranking for monitored protocols, used as reference for risk weighting:

| Rank | Protocol | Network | Reference APY | Safety Score | Primary Risks |
|---|---|---|---|---|---|
| 1 | Aave V3 USDC Supply | Base | ~3.17% | 8.8/10 | Shared pool bad debt, utilization, Base risk |
| 2 | Sky sUSDS | Ethereum | ~3.75% | 8.5/10 | USDC→USDS conversion, governance, RWA exposure |
| 3 | Morpho Steakhouse Prime USDC | Base | ~3.5-4.0% | 8.3/10 | Curator, underlying market bad debt |
| 4 | Morpho Gauntlet USDC Prime | Base | ~4.0% | 8.2/10 | Curator, oracle, market allocation |
| 5 | Compound V3 USDC | Base/Ethereum | ~3-5% | 8.1/10 | Single collateral market risk, utilization |
| 6 | Fluid USDC Lending | Ethereum | ~5.4% | 7.8/10 | Complex contract system, utilization |
| 7 | Morpho Pangolins USDC | Base | ~4.07% | 7.5/10 | Pangolins management capability, rebalancing |
| 8 | Morpho Gauntlet Frontier USDC | Ethereum | ~5.36% | 7.4/10 | Broader collateral acceptance for yield |
| 9 | Jupiter Lend USDC | Solana | ~4.0-4.25% | 7.2/10 | Newer protocol, unified liquidity, withdrawal smoothing |
| 10 | Kamino USDC Lending | Solana | ~varies | 7.2/10 | Solana, oracle, liquidation, market parameters |

**Note:** Safety scores are baseline references as of 2026-06-15. Real-time risk assessment by the risk engine may differ based on current on-chain conditions.

---

## 12. Implementation Notes (from spec review)

### Morpho Borrower Enumeration (Layer M5)

Enumerating all borrowers per market via RPC is impractical. Approach:
- **Primary:** Use Morpho Blue subgraph (The Graph / Goldsky) to query active borrowers per market
- **Fallback:** Index Supply/Borrow/Repay/Liquidate events from market creation block, maintain local borrower set in SQLite
- **Optimization:** Only track borrowers with health_factor < 2.0 (pruned set for stress testing)
- Add `events/indexer.py` module for event subscription and catchup

### Reserve Monitoring Data Sources (Stablecoin Layer 4)

- **USDC:** DefiLlama stablecoin API for circulating supply per chain; Circle transparency page scrape (monthly attestation PDF) with manual override config
- **USDT:** DefiLlama stablecoin API; Tether transparency page scrape; manual `config/reserves_override.yaml` for quarterly report data
- **Report delay detection:** Track last-known report date in DB; compare against expected cadence (Circle: monthly, Tether: quarterly)
- Accept that this layer has lower automation — manual review supplements automated checks

### Morpho Collector Structure (refactored)

Shared Morpho abstractions across chains to avoid duplication:

```
collectors/morpho/
├── base_morpho.py          # Shared: vault reading, market parsing, oracle check
├── models.py               # MorphoMarketAllocation, VaultState, OracleHealth
├── vault.py                # Vault shares, allocation, queue, version detection
├── market.py               # Per-market utilization, liquidity, LLTV
├── oracle.py               # Oracle health, cross-validation
├── bad_debt.py             # Borrower risk, stress test
├── governance.py           # Curator/owner/allocator events
├── withdrawal_sim.py       # 10%/50%/100% withdrawal simulation
├── adapters.py             # V2 adapter monitoring
├── chain_base.py           # Base-specific: vault addresses, sequencer check
└── chain_ethereum.py       # Ethereum-specific: vault addresses
```

### Vault Version Detection

```python
async def detect_vault_version(vault_address: str, w3: Web3) -> str:
    # V2 has adapter-related functions
    try:
        await call_contract(vault_address, "adapterRegistry()")
        return "v2"
    except:
        pass
    # V1.1 has specific storage layout differences
    try:
        await call_contract(vault_address, "config()")  # V1.1-only
        return "v1.1"
    except:
        return "v1.0"
```

### Database Retention Policy

| Data | Raw Retention | Aggregation |
|---|---|---|
| Positions & metrics | 7 days | 1-min avg → 30 days, hourly avg → forever |
| Alerts | Forever | — |
| Stablecoin prices | 7 days | 1-min → 30 days |
| Protocol stats | 30 days | hourly → forever |

- WAL checkpoint every 5 minutes
- VACUUM weekly via scheduled task
- Monitor DB file size; warn if >500MB

### Secrets & Config

- `.env` for bootstrap-level config only: `DATABASE_URL`, `API_HOST`, `API_PORT`
- All user-facing config (wallets, RPC keys, thresholds, protocols, Telegram) stored in DB
- `config/seed.yaml` imported into DB on first startup when config tables are empty
- RPC API keys stored as plaintext in DB (personal tool; encrypt if needed later)
- Frontend served by FastAPI in production (static files), Vite dev server in development

### Telegram Rate Limiting

- Notifier maintains internal queue with 1 msg/sec rate limit per chat
- Burst events (flash crash + multiple liquidations): batch into single summary message if >5 alerts within 30 sec
- `/mute <rule> <duration>` command via Telegram Bot for suppressing known issues

### Stablecoin Layer 3 Chain Scope

Layer 3 (supply monitoring) covers: Ethereum, Base, Solana, BSC (matching monitored chains). Arbitrum, Optimism, and Tron tracked as aggregate via DefiLlama stablecoin API only — no direct RPC, no dedicated collectors.

### Depeg Threshold Reconciliation

| Source | Threshold | Meaning |
|---|---|---|
| §4 Risk Engine defaults | >0.5% warning, >2% critical | Generic rule defaults |
| §5 Layer 1 detection | >0.3%+10min caution, >0.5%+5min warning, >1% immediate critical | Stablecoin-specific with duration |
| §5 Hard trigger | <$0.98 (2%) | Bypasses all scoring, immediate action |

Layer 1 detection is the authoritative source for stablecoin depeg. §4 defaults are overridden by the stablecoin-specific rules. Hard trigger is the last line of defense.
