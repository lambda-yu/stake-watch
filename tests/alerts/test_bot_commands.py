"""Tests for the interactive Telegram command bot."""
from __future__ import annotations

from stake_watch.alerts.bot_commands import format_help


# ---------- format_help ----------

def test_format_help_lists_all_four_commands():
    text = format_help()
    for cmd in ("/help", "/protocols", "/compare", "/protocol <"):
        assert cmd in text, f"missing {cmd} in help output"
