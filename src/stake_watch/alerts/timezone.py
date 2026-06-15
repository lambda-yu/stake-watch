from __future__ import annotations

from datetime import datetime, timezone, timedelta

DEFAULT_TZ_OFFSET = 8  # UTC+8 (Asia/Shanghai)


def get_display_tz(offset_hours: int = DEFAULT_TZ_OFFSET) -> timezone:
    return timezone(timedelta(hours=offset_hours))


def format_time(dt: datetime, offset_hours: int = DEFAULT_TZ_OFFSET) -> str:
    tz = get_display_tz(offset_hours)
    local = dt.astimezone(tz)
    sign = "+" if offset_hours >= 0 else ""
    return local.strftime(f"%Y-%m-%d %H:%M UTC{sign}{offset_hours}")


def now_display(offset_hours: int = DEFAULT_TZ_OFFSET) -> str:
    return format_time(datetime.now(timezone.utc), offset_hours)
