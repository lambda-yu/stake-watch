# API Endpoints

All endpoints are under the `/api` prefix. Authoritative source is the FastAPI router code in `src/stake_watch/api/`; this file is a quick reference.

## Status

| Method | Path                    | Purpose                                         |
| ------ | ----------------------- | ----------------------------------------------- |
| GET    | `/api/status`           | Service health + scheduler liveness.            |
| GET    | `/api/status/collectors`| Last-run timestamp and error per collector.     |

## Config (Settings page)

| Method | Path                    | Purpose                                         |
| ------ | ----------------------- | ----------------------------------------------- |
| GET    | `/api/config`           | Return all config (wallets, intervals, thresholds, Telegram token presence). |
| PATCH  | `/api/config`           | Partial update of the config blob.              |
| GET    | `/api/config/wallets`   | List monitored wallets across chains.           |
| POST   | `/api/config/wallets`   | Add a wallet `{ chain, address, label? }`.      |
| DELETE | `/api/config/wallets/{id}` | Remove a wallet.                             |

## Protocols (Protocols page)

| Method | Path                          | Purpose                                   |
| ------ | ----------------------------- | ----------------------------------------- |
| GET    | `/api/protocols`              | List all configured protocols.            |
| POST   | `/api/protocols`              | Add a protocol `{ slug, chain, collector, params, enabled }`. |
| GET    | `/api/protocols/{id}`         | Get one protocol's full config.           |
| PATCH  | `/api/protocols/{id}`         | Edit params, label, or thresholds.        |
| POST   | `/api/protocols/{id}/toggle`  | Enable / disable without deleting.        |
| DELETE | `/api/protocols/{id}`         | Remove a protocol and its rules.          |

## Positions & stats (Dashboard page)

| Method | Path                          | Purpose                                   |
| ------ | ----------------------------- | ----------------------------------------- |
| GET    | `/api/positions`              | Latest snapshot of all positions.         |
| GET    | `/api/positions?protocol=...` | Filter by protocol slug.                  |
| GET    | `/api/protocol-stats`         | Latest TVL / APY / utilization per protocol. |

## Alerts

| Method | Path                          | Purpose                                   |
| ------ | ----------------------------- | ----------------------------------------- |
| GET    | `/api/alerts`                 | Recent alerts (paginated).                |
| GET    | `/api/alerts?unresolved=true` | Open alerts only.                         |
| POST   | `/api/alerts/{id}/ack`        | Acknowledge / clear an alert.             |
| POST   | `/api/alerts/test`            | Send a test message via the Telegram notifier. |

## Notes

- Endpoint shapes and exact field names should be verified against `src/stake_watch/api/` before relying on them in code.
- Schemas are Pydantic models living next to the routers; reuse them in tests via the FastAPI test client.
