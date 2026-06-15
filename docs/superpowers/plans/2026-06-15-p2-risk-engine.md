# Stake Watch P2: Risk Engine + Telegram Alerts

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the risk evaluation engine that processes collected data against configurable rules, and push alerts via Telegram Bot with severity levels and cooldown deduplication.

**Architecture:** Risk engine evaluates rules after each collection cycle. Alert model persists to DB. Telegram notifier sends formatted messages with rate limiting. Cooldown tracker prevents duplicate alerts.

**Tech Stack:** python-telegram-bot (async), existing pydantic/sqlalchemy/storage

**Depends on:** P1a + P1b + P1-morpho complete (44 tests passing)

---

## Chunk 1: Alert Model + Risk Engine Core

### Task R1: Alert model + DB table

**Files:**
- Create: `src/stake_watch/models/alert.py`
- Modify: `src/stake_watch/storage/tables.py` — add AlertRow
- Modify: `src/stake_watch/storage/db.py` — add save_alert(), get_recent_alerts()
- Test: `tests/models/test_alert.py`
- Test: `tests/storage/test_alerts.py`

- [ ] **Step 1: Write tests**

```python
# tests/models/test_alert.py
from datetime import datetime, timezone
from stake_watch.models.alert import Alert, Severity, RuleType

def test_alert_creation():
    a = Alert(rule_type=RuleType.LIQUIDATION, severity=Severity.CRITICAL,
        protocol="jupiter_lend", chain="solana", title="Liquidation Risk",
        message="Health factor 1.08", details={"health_factor": 1.08},
        created_at=datetime.now(timezone.utc))
    assert a.severity == Severity.CRITICAL
    assert a.rule_type == RuleType.LIQUIDATION

def test_alert_key():
    a = Alert(rule_type=RuleType.LIQUIDATION, severity=Severity.WARNING,
        protocol="aave_v3_base", chain="base", title="Test",
        message="test", created_at=datetime.now(timezone.utc))
    assert a.dedup_key == "liquidation:aave_v3_base:base"
```

```python
# tests/storage/test_alerts.py
from datetime import datetime, timezone
import pytest
from stake_watch.models.alert import Alert, Severity, RuleType
from stake_watch.storage.db import Storage

@pytest.fixture
async def storage(tmp_path):
    s = Storage(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    await s.initialize()
    yield s
    await s.close()

@pytest.mark.asyncio
async def test_save_and_get_alerts(storage):
    alert = Alert(rule_type=RuleType.PROTOCOL_EVENT, severity=Severity.WARNING,
        protocol="aave_v3_base", chain="base", title="TVL Drop",
        message="TVL dropped 20%", created_at=datetime.now(timezone.utc))
    await storage.save_alert(alert)
    alerts = await storage.get_recent_alerts(limit=10)
    assert len(alerts) == 1
    assert alerts[0].title == "TVL Drop"
```

- [ ] **Step 2: Implement Alert model**

```python
# src/stake_watch/models/alert.py
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
```

- [ ] **Step 3: Add AlertRow to tables.py, save/get to db.py**

Append to `tables.py`:
```python
class AlertRow(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rule_type: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(String(20))
    protocol: Mapped[str] = mapped_column(String(100))
    chain: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedup_key: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

Add to `db.py`:
```python
async def save_alert(self, alert: Alert): ...
async def get_recent_alerts(self, limit: int = 50) -> list[Alert]: ...
```

- [ ] **Step 4: Run tests, commit**
```bash
git commit -m "feat: add Alert model with severity/dedup and DB persistence"
```

---

### Task R2: Risk engine core — BaseRule + RuleEngine

**Files:**
- Create: `src/stake_watch/risk/__init__.py`
- Create: `src/stake_watch/risk/engine.py`
- Create: `src/stake_watch/risk/rules/base.py`
- Test: `tests/risk/__init__.py`
- Test: `tests/risk/test_engine.py`

- [ ] **Step 1: Write tests**

```python
# tests/risk/test_engine.py
from datetime import datetime, timedelta, timezone
from stake_watch.models.alert import Alert, Severity, RuleType
from stake_watch.risk.engine import RuleEngine, CooldownTracker
from stake_watch.risk.rules.base import BaseRule, RuleContext
import pytest

class FakeRule(BaseRule):
    rule_type = RuleType.PROTOCOL_EVENT
    severity = Severity.WARNING
    cooldown = timedelta(hours=1)
    def evaluate(self, context: RuleContext) -> Alert | None:
        if context.get("tvl_drop", 0) > 0.15:
            return Alert(rule_type=self.rule_type, severity=self.severity,
                protocol=context["protocol"], chain=context["chain"],
                title="TVL Crash", message=f"TVL dropped {context['tvl_drop']:.0%}",
                created_at=datetime.now(timezone.utc))
        return None

def test_engine_evaluates_rules():
    engine = RuleEngine(rules=[FakeRule()])
    ctx = {"protocol": "aave", "chain": "base", "tvl_drop": 0.20}
    alerts = engine.evaluate(ctx)
    assert len(alerts) == 1
    assert alerts[0].title == "TVL Crash"

def test_engine_no_alert_below_threshold():
    engine = RuleEngine(rules=[FakeRule()])
    ctx = {"protocol": "aave", "chain": "base", "tvl_drop": 0.05}
    alerts = engine.evaluate(ctx)
    assert len(alerts) == 0

def test_cooldown_blocks_duplicate():
    tracker = CooldownTracker()
    alert = Alert(rule_type=RuleType.PROTOCOL_EVENT, severity=Severity.WARNING,
        protocol="aave", chain="base", title="TVL", message="test",
        created_at=datetime.now(timezone.utc))
    assert tracker.should_send(alert, cooldown=timedelta(hours=1)) is True
    tracker.record(alert)
    assert tracker.should_send(alert, cooldown=timedelta(hours=1)) is False

def test_cooldown_expires():
    tracker = CooldownTracker()
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    alert = Alert(rule_type=RuleType.PROTOCOL_EVENT, severity=Severity.WARNING,
        protocol="aave", chain="base", title="TVL", message="test",
        created_at=old_time)
    tracker.record(alert)
    new_alert = Alert(rule_type=RuleType.PROTOCOL_EVENT, severity=Severity.WARNING,
        protocol="aave", chain="base", title="TVL", message="test",
        created_at=datetime.now(timezone.utc))
    assert tracker.should_send(new_alert, cooldown=timedelta(hours=1)) is True
```

- [ ] **Step 2: Implement**

```python
# src/stake_watch/risk/rules/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import timedelta
from stake_watch.models.alert import Alert, Severity, RuleType

RuleContext = dict

class BaseRule(ABC):
    rule_type: RuleType
    severity: Severity
    cooldown: timedelta

    @abstractmethod
    def evaluate(self, context: RuleContext) -> Alert | None: ...
```

```python
# src/stake_watch/risk/engine.py
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from stake_watch.models.alert import Alert, Severity
from stake_watch.risk.rules.base import BaseRule, RuleContext

COOLDOWN_MAP = {
    Severity.CRITICAL: timedelta(minutes=15),
    Severity.WARNING: timedelta(hours=1),
    Severity.INFO: timedelta(hours=6),
}

class CooldownTracker:
    def __init__(self):
        self._last_sent: dict[str, datetime] = {}

    def should_send(self, alert: Alert, cooldown: timedelta | None = None) -> bool:
        cd = cooldown or COOLDOWN_MAP.get(alert.severity, timedelta(hours=1))
        last = self._last_sent.get(alert.dedup_key)
        if last is None:
            return True
        return (datetime.now(timezone.utc) - last) >= cd

    def record(self, alert: Alert):
        self._last_sent[alert.dedup_key] = alert.created_at

class RuleEngine:
    def __init__(self, rules: list[BaseRule] | None = None):
        self.rules = rules or []
        self.cooldown = CooldownTracker()

    def evaluate(self, context: RuleContext) -> list[Alert]:
        alerts = []
        for rule in self.rules:
            try:
                alert = rule.evaluate(context)
                if alert and self.cooldown.should_send(alert, rule.cooldown):
                    alerts.append(alert)
                    self.cooldown.record(alert)
            except Exception:
                pass
        return alerts
```

- [ ] **Step 3: Run tests, commit**
```bash
git commit -m "feat: add risk engine with BaseRule, RuleEngine, and cooldown tracker"
```

---

## Chunk 2: Rule Implementations

### Task R3: Built-in rules (liquidation, protocol event, yield change, Morpho)

**Files:**
- Create: `src/stake_watch/risk/rules/liquidation.py`
- Create: `src/stake_watch/risk/rules/protocol_event.py`
- Create: `src/stake_watch/risk/rules/yield_change.py`
- Create: `src/stake_watch/risk/rules/morpho.py`
- Test: `tests/risk/test_rules.py`

- [ ] **Step 1: Write tests for each rule**

```python
# tests/risk/test_rules.py
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from stake_watch.risk.rules.liquidation import LiquidationWarningRule, LiquidationCriticalRule
from stake_watch.risk.rules.protocol_event import TvlCrashRule, CollectorFailureRule
from stake_watch.risk.rules.yield_change import ApySwingRule
from stake_watch.risk.rules.morpho import (
    MorphoUtilizationRule, MorphoWithdrawalRule, MorphoSharePriceRule)

def test_liquidation_warning():
    rule = LiquidationWarningRule()
    alert = rule.evaluate({"protocol": "aave", "chain": "base", "health_factor": 1.2})
    assert alert is not None
    assert alert.severity.value == "warning"

def test_liquidation_critical():
    rule = LiquidationCriticalRule()
    alert = rule.evaluate({"protocol": "aave", "chain": "base", "health_factor": 1.05})
    assert alert is not None
    assert alert.severity.value == "critical"

def test_liquidation_safe():
    rule = LiquidationWarningRule()
    alert = rule.evaluate({"protocol": "aave", "chain": "base", "health_factor": 1.5})
    assert alert is None

def test_tvl_crash():
    rule = TvlCrashRule()
    alert = rule.evaluate({"protocol": "aave", "chain": "base", "tvl_change_1h": -0.20})
    assert alert is not None
    assert alert.severity.value == "critical"

def test_tvl_stable():
    rule = TvlCrashRule()
    assert rule.evaluate({"protocol": "aave", "chain": "base", "tvl_change_1h": -0.05}) is None

def test_apy_swing():
    rule = ApySwingRule()
    alert = rule.evaluate({"protocol": "aave", "chain": "base", "apy_change_24h": 0.50})
    assert alert is not None

def test_collector_failure():
    rule = CollectorFailureRule()
    alert = rule.evaluate({"protocol": "aave", "chain": "base", "consecutive_failures": 3})
    assert alert is not None

def test_morpho_utilization():
    rule = MorphoUtilizationRule()
    alert = rule.evaluate({"protocol": "morpho", "chain": "base", "max_utilization": 0.95})
    assert alert is not None

def test_morpho_withdrawal_fail():
    rule = MorphoWithdrawalRule()
    alert = rule.evaluate({"protocol": "morpho", "chain": "base",
        "can_withdraw_10pct": False, "liquidity_ratio": 0.05})
    assert alert is not None
    assert alert.severity.value == "critical"

def test_morpho_share_price_drop():
    rule = MorphoSharePriceRule()
    alert = rule.evaluate({"protocol": "morpho", "chain": "base",
        "share_price_change": -0.001})
    assert alert is not None
    assert alert.severity.value == "critical"
```

- [ ] **Step 2: Implement rules**

Each rule is a small class inheriting BaseRule with an evaluate() method. Implementation follows the spec thresholds exactly.

Liquidation rules: health_factor < 1.3 warning, < 1.1 critical
TVL crash: tvl_change_1h < -0.15 critical
APY swing: abs(apy_change_24h) > 0.30 info
Collector failure: consecutive_failures >= 3 warning
Morpho utilization: max_utilization > 0.92 warning
Morpho withdrawal: can_withdraw_10pct == False critical
Morpho share price: share_price_change < 0 critical

- [ ] **Step 3: Run tests, commit**
```bash
git commit -m "feat: add built-in risk rules (liquidation, TVL crash, APY, Morpho)"
```

---

## Chunk 3: Telegram Notifier

### Task R4: Telegram Bot notifier

**Files:**
- Create: `src/stake_watch/alerts/__init__.py`
- Create: `src/stake_watch/alerts/base.py`
- Create: `src/stake_watch/alerts/telegram.py`
- Create: `src/stake_watch/alerts/formatter.py`
- Test: `tests/alerts/__init__.py`
- Test: `tests/alerts/test_telegram.py`
- Test: `tests/alerts/test_formatter.py`

- [ ] **Step 1: Add python-telegram-bot**
```bash
uv add python-telegram-bot
```

- [ ] **Step 2: Write tests**

Test formatter produces expected message format. Test notifier calls telegram API (mocked).

```python
# tests/alerts/test_formatter.py
from datetime import datetime, timezone
from stake_watch.alerts.formatter import format_alert
from stake_watch.models.alert import Alert, Severity, RuleType

def test_format_critical():
    a = Alert(rule_type=RuleType.LIQUIDATION, severity=Severity.CRITICAL,
        protocol="jupiter_lend", chain="solana", title="Liquidation Risk",
        message="Health factor 1.08", details={"health_factor": 1.08},
        created_at=datetime.now(timezone.utc))
    text = format_alert(a)
    assert "[CRITICAL]" in text
    assert "Liquidation Risk" in text
    assert "jupiter_lend" in text
```

```python
# tests/alerts/test_telegram.py
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import pytest
from stake_watch.alerts.telegram import TelegramNotifier
from stake_watch.models.alert import Alert, Severity, RuleType

@pytest.mark.asyncio
async def test_telegram_send():
    notifier = TelegramNotifier(bot_token="fake-token", chat_id="123")
    alert = Alert(rule_type=RuleType.PROTOCOL_EVENT, severity=Severity.WARNING,
        protocol="aave", chain="base", title="Test", message="test msg",
        created_at=datetime.now(timezone.utc))
    with patch("telegram.Bot.send_message", new_callable=AsyncMock) as mock_send:
        result = await notifier.send(alert)
    assert result is True
    mock_send.assert_called_once()
```

- [ ] **Step 3: Implement**

```python
# src/stake_watch/alerts/base.py
from abc import ABC, abstractmethod
from stake_watch.models.alert import Alert

class BaseNotifier(ABC):
    @abstractmethod
    async def send(self, alert: Alert) -> bool: ...
```

```python
# src/stake_watch/alerts/formatter.py
from stake_watch.models.alert import Alert, Severity

SEVERITY_EMOJI = {Severity.CRITICAL: "🔴", Severity.WARNING: "🟡", Severity.INFO: "🔵"}

def format_alert(alert: Alert) -> str:
    emoji = SEVERITY_EMOJI.get(alert.severity, "")
    return (
        f"{emoji} [{alert.severity.value.upper()}] {alert.title}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Chain: {alert.chain} | Protocol: {alert.protocol}\n"
        f"{alert.message}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
```

```python
# src/stake_watch/alerts/telegram.py
from __future__ import annotations
import logging
from telegram import Bot
from stake_watch.alerts.base import BaseNotifier
from stake_watch.alerts.formatter import format_alert
from stake_watch.models.alert import Alert

logger = logging.getLogger(__name__)

class TelegramNotifier(BaseNotifier):
    def __init__(self, bot_token: str, chat_id: str):
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id

    async def send(self, alert: Alert) -> bool:
        text = format_alert(alert)
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=text)
            return True
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False
```

- [ ] **Step 4: Run tests, commit**
```bash
git commit -m "feat: add Telegram notifier with alert formatting and severity emoji"
```

---

## Chunk 4: Pipeline Integration

### Task R5: Wire risk engine into collection cycle

**Files:**
- Modify: `src/stake_watch/scheduler/runner.py` — add risk evaluation after collection
- Create: `src/stake_watch/risk/rules/__init__.py` — default rule set factory
- Modify: `src/stake_watch/main.py` — wire risk engine + notifier
- Test: `tests/risk/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/risk/test_integration.py
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest
from stake_watch.collectors.base import CollectResult
from stake_watch.models.common import Chain
from stake_watch.models.protocol import PoolStats, ProtocolStats
from stake_watch.risk.engine import RuleEngine
from stake_watch.risk.rules.protocol_event import TvlCrashRule

@pytest.mark.asyncio
async def test_risk_evaluation_after_collection():
    engine = RuleEngine(rules=[TvlCrashRule()])
    ctx = {"protocol": "aave_v3_base", "chain": "base", "tvl_change_1h": -0.25}
    alerts = engine.evaluate(ctx)
    assert len(alerts) == 1
    assert alerts[0].severity.value == "critical"
```

- [ ] **Step 2: Create default rule set**
```python
# src/stake_watch/risk/rules/__init__.py
from stake_watch.risk.rules.liquidation import LiquidationWarningRule, LiquidationCriticalRule
from stake_watch.risk.rules.protocol_event import TvlCrashRule, CollectorFailureRule
from stake_watch.risk.rules.yield_change import ApySwingRule
from stake_watch.risk.rules.morpho import MorphoUtilizationRule, MorphoWithdrawalRule, MorphoSharePriceRule

def get_default_rules():
    return [
        LiquidationCriticalRule(),
        LiquidationWarningRule(),
        TvlCrashRule(),
        CollectorFailureRule(),
        ApySwingRule(),
        MorphoUtilizationRule(),
        MorphoWithdrawalRule(),
        MorphoSharePriceRule(),
    ]
```

- [ ] **Step 3: Add alert API route for frontend**

Create `src/stake_watch/api/routes/alerts.py`:
```python
from fastapi import APIRouter, Depends
from stake_watch.api.deps import get_storage
from stake_watch.storage.db import Storage

router = APIRouter()

@router.get("")
async def list_alerts(limit: int = 50, storage: Storage = Depends(get_storage)):
    alerts = await storage.get_recent_alerts(limit=limit)
    return [a.model_dump(mode="json") for a in alerts]
```

Register in `app.py`:
```python
from stake_watch.api.routes import config, protocols, status, alerts
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
```

- [ ] **Step 4: Run all tests, commit**
```bash
git commit -m "feat: wire risk engine into pipeline with default rules and alert API"
```

---

## Summary

| Task | What it builds |
|---|---|
| R1 | Alert model + DB persistence |
| R2 | RuleEngine + CooldownTracker + BaseRule |
| R3 | 8 built-in rules (liquidation x2, TVL crash, collector failure, APY swing, Morpho x3) |
| R4 | Telegram notifier with formatted messages |
| R5 | Pipeline integration + default rule set + alert API endpoint |
