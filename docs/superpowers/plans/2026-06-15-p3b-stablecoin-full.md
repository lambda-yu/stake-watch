# Stake Watch P3b: Full 8-Layer Stablecoin Module + Scoring

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan.

**Goal:** Complete all 8 stablecoin monitoring layers + 7-dimension composite scoring model with hard triggers.

**Depends on:** P3a (105 tests)

---

## Layer Status

| Layer | P3a | P3b | Data Source |
|---|---|---|---|
| 1. Price Depeg | ✅ Done | Enhance with exchange-level prices | CoinGecko tickers |
| 2. DEX Liquidity | - | ⚠️ Stub (on-chain deferred) | Placeholder |
| 3. Supply & Redemption | ✅ Done | Already complete | DefiLlama |
| 4. Reserve Monitoring | - | Manual override + tracking | Config + DefiLlama |
| 5. Blacklist Check | - | ✅ On-chain eth_call | web3.py |
| 6. Cross-Chain Verify | - | ✅ Whitelist check | Static config |
| 7. CEX Spread | - | ✅ Multi-exchange prices | CoinGecko tickers |
| 8. Protocol Exposure | ✅ Existing | Already in collectors | Existing |
| Scoring | - | ✅ 7-dim weighted model | Aggregation |

---

## Tasks

### Task B1: CEX spread collector (Layer 7)

CoinGecko tickers API → extract `converted_last.usd` per exchange → calculate spread.

**Files:**
- Create: `src/stake_watch/collectors/stablecoin/cex_spread.py`
- Test: `tests/collectors/stablecoin/test_cex_spread.py`

**Implementation:** Fetch `/coins/{id}/tickers`, filter `is_stale=false`, `is_anomaly=false`, extract `converted_last.usd` per exchange, compute max-min spread.

### Task B2: Blacklist check (Layer 5) + Cross-chain whitelist (Layer 6)

**Files:**
- Create: `src/stake_watch/collectors/stablecoin/blacklist.py`
- Create: `src/stake_watch/collectors/stablecoin/cross_chain.py`
- Create: `config/stablecoins.yaml` — whitelist registry
- Tests for each

**Blacklist:** Call `isBlacklisted(address)` / `isBlackListed(address)` via eth_call on USDC/USDT contracts per chain.

**Cross-chain:** Compare token contract addresses against whitelist. Flag unknown addresses.

### Task B3: Composite scoring model

**Files:**
- Create: `src/stake_watch/risk/stablecoin_scorer.py`
- Test: `tests/risk/test_stablecoin_scorer.py`

7-dimension weighted score (0-100):
- Depeg risk: 25%
- DEX liquidity: 15% (placeholder returns 0)
- Redemption pressure: 15%
- Reserve risk: 20% (placeholder returns 0)
- Issuer & regulatory: 10% (placeholder returns 0)
- On-chain contract risk: 10%
- Cross-chain version: 5%

8 hard triggers bypass scoring → immediate CRITICAL.

### Task B4: Integration — wire all layers into scheduled pipeline + API

- Stablecoin collection orchestrator that runs all layers
- Update `/api/stablecoins` to return full scoring
- Add `risk_score` field to StablecoinRiskSnapshot

---
