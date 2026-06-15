from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from stake_watch.alerts.telegram import TelegramNotifier
from stake_watch.models.alert import Alert, Severity, RuleType

@pytest.mark.asyncio
async def test_telegram_send():
    notifier = TelegramNotifier(bot_token="fake-token", chat_id="123")
    alert = Alert(rule_type=RuleType.PROTOCOL_EVENT, severity=Severity.WARNING,
        protocol="aave", chain="base", title="Test", message="test msg",
        created_at=datetime.now(timezone.utc))

    mock_send = AsyncMock()
    with patch("telegram.Bot.send_message", mock_send):
        result = await notifier.send(alert)

    assert result is True
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args
    assert "123" in str(call_kwargs)

@pytest.mark.asyncio
async def test_telegram_send_failure():
    notifier = TelegramNotifier(bot_token="fake", chat_id="123")
    alert = Alert(rule_type=RuleType.PROTOCOL_EVENT, severity=Severity.WARNING,
        protocol="aave", chain="base", title="Test", message="test",
        created_at=datetime.now(timezone.utc))

    with patch("telegram.Bot.send_message", AsyncMock(side_effect=Exception("Network error"))):
        result = await notifier.send(alert)

    assert result is False
