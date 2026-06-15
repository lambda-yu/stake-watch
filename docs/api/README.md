# API Overview

The backend exposes a FastAPI REST API mounted at `/api/*`. It runs in the same process as the APScheduler collector loop (`src/stake_watch/main.py`).

## Base URL

```
http://localhost:8000/api
```

(Port is configurable via the DB config table.)

## Audience

The API is consumed by the React frontend (`frontend/`). It is **not** intended to be a public, multi-tenant API — there is no auth, and the server should not be exposed to the internet.

## Conventions

- All requests and responses are JSON.
- Datetimes are ISO-8601 UTC strings.
- Errors return standard FastAPI shape: `{ "detail": "<message>" }` with an appropriate 4xx/5xx status.
- Mutations (`POST`, `PATCH`, `DELETE`) return the updated resource (or `{ "ok": true }` for deletes).
- All config lives in the DB; mutating endpoints persist immediately and the scheduler picks up changes on the next tick.

## Module layout

```
src/stake_watch/api/
  config endpoints     # wallets, intervals, thresholds
  protocols endpoints  # add / edit / toggle / delete monitored protocols
  alerts endpoints     # recent alerts, mute / unmute
  status endpoints     # health, last-collection timestamps
```

See `docs/api/endpoints.md` for the full endpoint list.
