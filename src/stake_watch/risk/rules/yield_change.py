from datetime import datetime, timedelta, timezone
from stake_watch.models.alert import Alert, Severity, RuleType
from stake_watch.risk.rules.base import BaseRule, RuleContext


class ApySwingRule(BaseRule):
    rule_type = RuleType.YIELD_CHANGE
    severity = Severity.INFO
    cooldown = timedelta(hours=6)

    def evaluate(self, ctx: RuleContext) -> Alert | None:
        change = ctx.get("apy_change_24h", 0)
        if abs(change) > 0.30:
            direction = "increased" if change > 0 else "decreased"
            return Alert(
                rule_type=self.rule_type,
                severity=self.severity,
                protocol=ctx["protocol"],
                chain=ctx["chain"],
                title="APY Swing",
                message=f"APY {direction} {abs(change):.0%} in 24h",
                details={"apy_change_24h": change},
                created_at=datetime.now(timezone.utc),
            )
        return None
