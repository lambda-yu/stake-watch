# Stake Watch

Personal cross-chain DeFi yield monitoring and risk alerting tool. Tracks 10 lending / staking protocols across Solana, Ethereum, BSC, and Base; emits Telegram alerts on stablecoin depeg, vault share-price drops, governance changes, sequencer downtime, oracle staleness, and risk-level escalations.

**Status:** active development · **445 tests passing** · Python 3.12+ / React 19.

---

## What it does

- **Per-protocol live data**: APY, TVL, utilization, withdrawable ratio, supply/borrow caps pulled from official APIs (Morpho GraphQL, Aave GraphQL, Compound REST, Kamino REST, Jupiter REST) and on-chain (Sky `ssr()`, Chainlink, Pyth).
- **8-dimension risk model** (contract / market / liquidity / collateral-oracle / governance / stablecoin / chain / yield), with per-product curated baselines that get overridden by live signals (utilization, bad-debt ratio, oracle deviation, share-price drift, sequencer status, etc.).
- **Veto rules** for hard fails (depeg < $0.98, bad debt > 0.2%, oracle stale beyond 1.5× heartbeat, sequencer down > 10 min, 10% withdraw simulation fail …).
- **Telegram pushes**:
  - Veto-triggered alerts (CRITICAL)
  - Risk-level escalation A→B/C/D/E (WARNING, CRITICAL on E)
  - Collector failure after 3 consecutive failures (WARNING)
  - Periodic protocols APY/TVL report (configurable interval)
  - Periodic stablecoin risk report
- **React UI** with: Dashboard (KPIs + top risks + recent alerts), Protocols (per-protocol cards with risk radar), Comparison (cross-protocol composite scoring), Stablecoins, Alerts log, Notifications (Telegram bot setup), Settings.

---

## Quick start

```bash
# Install Python deps
uv sync

# One-time: install headless Chromium for "推送到 Telegram" screenshot button
uv run playwright install chromium

# Install frontend deps
cd frontend && npm install && cd ..

# Run backend (FastAPI + scheduler in one process, http://localhost:8000)
uv run python -m stake_watch.main

# In a separate shell — frontend dev server (proxies /api to :8000)
cd frontend && npm run dev   # http://localhost:5173

# Run the test suite
uv run pytest tests/
uv run pytest tests/ --cov=stake_watch
```

First boot reads `config/seed.yaml` and writes everything into `stake_watch.db`. After that, **all configuration is edited via the React UI** (Settings + Notifications + per-protocol cards) — don't hand-edit YAML at runtime.

---

## Architecture

```
src/stake_watch/
  models/          Pydantic: Position, ProtocolStats, Alert, StablecoinSnapshot
  collectors/      BaseCollector + protocol families (Morpho/Aave/Compound/Sky/Kamino/Jupiter/DefiLlama)
    registry.py    Scheduled-collector factory (positions + stats)
    refreshers.py  /api/protocols/refresh dispatcher (live APY/TVL fetchers)
  storage/         SQLAlchemy async + aiosqlite; positions, protocol_stats, alerts,
                   tvl_snapshots, vault_share_prices, app_settings, configs
    snapshots.py   Periodic TVL + share-price snapshot writers (scheduler job)
  risk/            risk_model.py (8-dim scoring + veto rules)
                   onchain_signals.py (Chainlink / Sequencer / Solana / Pyth)
                   protocol_status.py (live evaluation orchestrator)
                   protocol_risk_monitor.py (periodic alert sweep)
                   products.py (PRIMARY_PRODUCT registry)
                   stablecoin_scorer.py + rules/ (per-rule alert engine)
  alerts/          telegram.py notifier, protocols_report.py, stablecoin_report.py
  api/             FastAPI: /protocols, /alerts, /comparison, /stablecoins,
                   /status, /positions, /backup
  scheduler/       APScheduler — positions, snapshots, reports, risk monitor
  main.py          Entry point: build DB + scheduler + FastAPI in one process
frontend/          React 19 + Vite + Tailwind v4 (pages → API endpoints 1:1)
config/seed.yaml   First-time DB initialization data only
tests/             pytest-asyncio, 445 tests
```

### Scheduler jobs

| Job | Default interval | Setting key |
|---|---|---|
| `positions` | `intervals.positions` (300s) | `intervals.positions` |
| `stablecoin_report` | 1h | `stablecoin.report_interval` |
| `dex_liquidity` | 5m | `stablecoin.dex_liquidity_interval` |
| `reserves_fetch` | 6h | `stablecoin.reserves_fetch_interval` |
| `protocols_report` | 4h | `protocols.report_interval` |
| `snapshots` | 4h | `protocols.snapshots_interval` |
| `risk_monitor` | 1h | `risk_monitor.interval` |

All intervals are persisted in SQLite and editable via Settings page or `PUT /api/config/intervals`.

---

## Backup / export

- **Raw SQLite snapshot**: `GET /api/backup/sqlite` — streams the .db file
- **Portable JSON**: `GET /api/backup/json` — config + recent operational data (capped 500 alerts / 1000 snapshots)

---

## Development guide

- **TDD**: write the test first; target 80%+ coverage. Existing suite is the spec.
- **Commits**: conventional style with Claude co-author trailer. See `docs/git/commits.md`.
- **Branches**: `main`, `feature/*`, `fix/*`. See `docs/git/branches.md`.
- **Deployment**: see `docs/ops/deploy.md`.

Most deep docs:

| Topic | File |
|---|---|
| TDD workflow | `docs/testing/tdd.md` |
| API endpoints | `docs/api/endpoints.md` |
| Naming / formatting | `docs/code-style/*.md` |
| Review checklist | `docs/review/checklist.md` |
| Deployment | `docs/ops/deploy.md` |

For agent-context, see `claude.md` (project instructions for AI coding assistants).
