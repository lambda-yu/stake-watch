from stake_watch.alerts.timezone import format_time
from stake_watch.models.alert import Alert, Severity

SEVERITY_ICONS = {Severity.CRITICAL: "🔴", Severity.WARNING: "🟡", Severity.INFO: "🔵"}

def format_alert(alert: Alert, tz_offset: int = 8) -> str:
    icon = SEVERITY_ICONS.get(alert.severity, "")
    time_str = format_time(alert.created_at, tz_offset)
    return (
        f"{icon} [{alert.severity.value.upper()}] {alert.title}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Chain: {alert.chain} | Protocol: {alert.protocol}\n"
        f"{alert.message}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{time_str}"
    )


def format_tvl(v: float) -> str:
    """Format a USD TVL value with human-readable scale (K/M/B).

    Preserves the exact output of the previous ``protocols_report._format_tvl``
    so downstream reports stay identical after the migration.
    """
    if v >= 1e9:
        return f"${v/1e9:.2f}B"
    if v >= 1e6:
        return f"${v/1e6:.1f}M"
    if v >= 1e3:
        return f"${v/1e3:.0f}K"
    return f"${v:.0f}"
