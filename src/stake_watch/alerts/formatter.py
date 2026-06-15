from stake_watch.models.alert import Alert, Severity

SEVERITY_ICONS = {Severity.CRITICAL: "🔴", Severity.WARNING: "🟡", Severity.INFO: "🔵"}

def format_alert(alert: Alert) -> str:
    icon = SEVERITY_ICONS.get(alert.severity, "")
    return (
        f"{icon} [{alert.severity.value.upper()}] {alert.title}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Chain: {alert.chain} | Protocol: {alert.protocol}\n"
        f"{alert.message}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
