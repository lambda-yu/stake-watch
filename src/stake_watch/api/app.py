from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from stake_watch.api import deps
from stake_watch.api.routes import config, protocols, status, alerts, stablecoins
from stake_watch.storage.db import Storage

def create_app(storage: Storage) -> FastAPI:
    app = FastAPI(title="Stake Watch", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_methods=["*"], allow_headers=["*"])
    deps.init_deps(storage)
    app.include_router(config.router, prefix="/api/config", tags=["config"])
    app.include_router(protocols.router, prefix="/api/protocols", tags=["protocols"])
    app.include_router(status.router, prefix="/api/status", tags=["status"])
    app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
    app.include_router(stablecoins.router, prefix="/api/stablecoins", tags=["stablecoins"])
    return app
