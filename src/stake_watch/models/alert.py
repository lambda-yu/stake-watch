from __future__ import annotations
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, computed_field

class RuleType(str, Enum):
    LIQUIDATION = "liquidation"
    DEPEG = "depeg"
    PROTOCOL_EVENT = "protocol_event"
    YIELD_CHANGE = "yield_change"
    MORPHO = "morpho"
    COLLECTOR_FAILURE = "collector_failure"

class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"

class Alert(BaseModel):
    rule_type: RuleType
    severity: Severity
    protocol: str
    chain: str
    title: str
    message: str
    details: dict | None = None
    created_at: datetime

    @computed_field
    @property
    def dedup_key(self) -> str:
        return f"{self.rule_type.value}:{self.protocol}:{self.chain}"
