from __future__ import annotations
from pathlib import Path
import yaml
from pydantic import BaseModel

class WalletConfig(BaseModel):
    chain: str
    address: str

class RpcEndpoint(BaseModel):
    primary: str
    fallback: list[str] = []

class DatabaseConfig(BaseModel):
    url: str = "sqlite:///stake_watch.db"

class IntervalConfig(BaseModel):
    positions: int = 300
    protocol_stats: int = 900
    stablecoin_price: int = 60
    stablecoin_supply: int = 600
    reserves: int = 21600

class RiskConfig(BaseModel):
    liquidation_warning: float = 1.3
    liquidation_critical: float = 1.1
    depeg_warning: float = 0.005
    depeg_critical: float = 0.02
    tvl_crash_threshold: float = 0.15
    apy_change_threshold: float = 0.30

class TelegramConfig(BaseModel):
    bot_token: str = ""
    chat_id: str = ""

class AppSettings(BaseModel):
    wallets: list[WalletConfig] = []
    rpc: dict[str, RpcEndpoint] = {}
    database: DatabaseConfig = DatabaseConfig()
    intervals: IntervalConfig = IntervalConfig()
    risk: RiskConfig = RiskConfig()
    telegram: TelegramConfig = TelegramConfig()

class ProtocolEntry(BaseModel):
    name: str
    chain: str
    collector: str
    enabled: bool = True
    safety_rank: int | None = None
    safety_score: float | None = None
    reference_apy: str | None = None
    primary_risks: list[str] = []
    vault_address: str | None = None
    defillama_slug: str | None = None
    pool_filter: str | None = None

def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result

def load_settings(path: Path | None, local_path: Path | None = None) -> AppSettings:
    data: dict = {}
    if path and path.exists():
        data = yaml.safe_load(path.read_text()) or {}
    if local_path and local_path.exists():
        local_data = yaml.safe_load(local_path.read_text()) or {}
        data = _deep_merge(data, local_data)
    return AppSettings.model_validate(data)

def load_protocols(path: Path) -> list[ProtocolEntry]:
    raw = yaml.safe_load(path.read_text()) or {}
    entries = raw.get("protocols", [])
    return [ProtocolEntry.model_validate(e) for e in entries]
