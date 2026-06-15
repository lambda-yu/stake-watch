from datetime import datetime, timedelta, timezone
from stake_watch.models.alert import Alert, Severity, RuleType
from stake_watch.risk.rules.base import BaseRule, RuleContext


class TvlCrashRule(BaseRule):
    rule_type = RuleType.PROTOCOL_EVENT
    severity = Severity.CRITICAL
    cooldown = timedelta(minutes=15)

    def evaluate(self, ctx: RuleContext) -> Alert | None:
        change = ctx.get("tvl_change_1h", 0)
        if change < -0.15:
            return Alert(
                rule_type=self.rule_type,
                severity=self.severity,
                protocol=ctx["protocol"],
                chain=ctx["chain"],
                title="TVL Crash",
                message=f"TVL dropped {abs(change):.0%} in 1 hour",
                details={"tvl_change_1h": change},
                created_at=datetime.now(timezone.utc),
            )
        return None


class CollectorFailureRule(BaseRule):
    rule_type = RuleType.COLLECTOR_FAILURE
    severity = Severity.WARNING
    cooldown = timedelta(hours=1)

    def evaluate(self, ctx: RuleContext) -> Alert | None:
        failures = ctx.get("consecutive_failures", 0)
        if failures >= 3:
            return Alert(
                rule_type=self.rule_type,
                severity=self.severity,
                protocol=ctx["protocol"],
                chain=ctx["chain"],
                title="Collector Failing",
                message=f"{failures} consecutive collection failures",
                details={"consecutive_failures": failures},
                created_at=datetime.now(timezone.utc),
            )
        return None
