# Naming Conventions

## Python (`src/stake_watch/`, `tests/`)

- **Modules / packages:** `snake_case` (e.g., `collectors/morpho.py`).
- **Functions / methods / variables:** `snake_case` (e.g., `fetch_positions`, `health_factor`).
- **Classes:** `PascalCase` (e.g., `BaseCollector`, `MorphoCollector`, `RiskEngine`).
- **Constants / module-level config:** `UPPER_SNAKE_CASE` (e.g., `DEFAULT_INTERVAL_SECONDS`).
- **Private helpers:** leading underscore (`_normalize_apy`).
- **Pydantic models:** `PascalCase` matching the domain noun (`Position`, `ProtocolStats`, `Alert`).
- **Async functions:** same `snake_case`; no `async_` prefix.
- **Test files:** `test_<module>.py`; test functions `test_<behaviour>`.

## TypeScript (`frontend/`)

- **Functions / variables / hooks:** `camelCase` (e.g., `fetchProtocols`, `useAlerts`).
- **React components / classes / types / interfaces:** `PascalCase` (e.g., `ProtocolsPage`, `SettingsForm`, `type Position`).
- **Constants:** `UPPER_SNAKE_CASE` for true module-level constants; otherwise `camelCase`.
- **Files:** components `PascalCase.tsx`, hooks/utilities `camelCase.ts`.
- **API client functions:** verb-first (`getProtocols`, `createProtocol`, `toggleProtocol`).

## Cross-cutting

- Names should describe intent, not implementation. Prefer `is_position_unhealthy` over `check`.
- Protocol identifiers stay lowercase and stable (`morpho`, `aave`, `kamino`) — they are DB keys.
