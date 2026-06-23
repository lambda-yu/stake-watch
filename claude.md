# Stake Watch

Personal cross-chain DeFi yield monitoring and risk alerting tool. Monitors 10 lending/staking protocols across Solana, Ethereum, BSC, and Base. Provides dedicated USDC/USDT stablecoin risk assessment and deep Morpho monitoring.

**Status:** Active development. 185 tests passing.

## Tech Stack

- **Backend:** Python 3.12+, FastAPI, SQLAlchemy (async) + aiosqlite, APScheduler, httpx, web3.py, solana-py, python-telegram-bot
- **Frontend:** React 18 + TypeScript, Vite, Tailwind CSS
- **DB:** SQLite (all config DB-stored, managed via React UI)
- **Tooling:** uv (Python), npm (frontend), pytest + pytest-asyncio

## Quick Commands

```bash
uv run python -m stake_watch.main         # Backend (FastAPI + scheduler in one process)
cd frontend && npm run dev                # Frontend dev server
uv run pytest tests/ -v                   # Run tests
uv run pytest tests/ --cov=stake_watch    # Coverage
```

## Directory Structure

```
src/stake_watch/
  models/          # Pydantic: Position, ProtocolStats, Alert
  collectors/      # BaseCollector -> DefiLlama, Morpho, Aave, Compound, Sky, Kamino
    registry.py    # Collector factory (dispatches by protocol config)
  storage/         # SQLAlchemy async: positions, protocol_stats, alerts, config
  risk/            # Rule evaluation + cooldown tracker
  alerts/          # Telegram notifier with formatting
  api/             # FastAPI REST endpoints (config CRUD, protocols, alerts, status)
  scheduler/       # APScheduler periodic collection
  main.py          # Entry point: FastAPI + scheduler
frontend/          # React SPA — Settings, Protocols, Dashboard pages
config/seed.yaml   # First-time DB initialization data
tests/             # pytest suite
```

## Architecture Overview

Single-process backend runs FastAPI and APScheduler together. The scheduler periodically invokes collectors (dispatched by `collectors/registry.py` based on each protocol's config row); collectors write `Position` and `ProtocolStats` rows. The risk engine evaluates rules against the latest snapshot, respecting per-alert cooldowns, and emits to the Telegram notifier. All configuration (wallets, intervals, thresholds, protocol toggles) lives in SQLite and is edited from the React frontend, which talks to FastAPI under `/api/*`.

## Development Guidelines

- **TDD:** Write the test first; implement until green. Target 80%+ coverage. See `docs/testing/tdd.md`.
- **Commits:** Conventional commit style with a Claude co-author trailer. See `docs/git/commits.md`.
- **Branches:** `main`, `feature/*`, `fix/*`. See `docs/git/branches.md`.
- **Config changes:** Edit through the frontend (DB-backed), not by hand-editing files. `config/seed.yaml` is only for first-time bootstrap.

## Progressive Doc Loading

Load deeper docs only when relevant to the task:

| Topic                 | File                              |
| --------------------- | --------------------------------- |
| Commit conventions    | `docs/git/commits.md`             |
| Branch naming         | `docs/git/branches.md`            |
| Git workflow          | `docs/git/workflow.md`            |
| Naming conventions    | `docs/code-style/naming.md`       |
| Formatting            | `docs/code-style/formatting.md`   |
| Linting               | `docs/code-style/linting.md`      |
| Code review checklist | `docs/review/checklist.md`        |
| Review process        | `docs/review/process.md`          |
| TDD workflow          | `docs/testing/tdd.md`             |
| API overview          | `docs/api/README.md`              |
| API endpoints         | `docs/api/endpoints.md`           |
