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
