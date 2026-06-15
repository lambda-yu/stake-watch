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
