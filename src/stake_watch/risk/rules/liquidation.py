from datetime import datetime, timedelta, timezone
from stake_watch.models.alert import Alert, Severity, RuleType
from stake_watch.risk.rules.base import BaseRule, RuleContext


class LiquidationWarningRule(BaseRule):
    rule_type = RuleType.LIQUIDATION
    severity = Severity.WARNING
    cooldown = timedelta(hours=1)

    def evaluate(self, ctx: RuleContext) -> Alert | None:
        hf = ctx.get("health_factor")
        if hf is not None and 1.1 <= hf < 1.3:
            return Alert(
                rule_type=self.rule_type,
                severity=self.severity,
                protocol=ctx["protocol"],
                chain=ctx["chain"],
                title="Liquidation Warning",
                message=f"Health factor {hf:.2f} approaching threshold",
                details={"health_factor": hf},
                created_at=datetime.now(timezone.utc),
            )
        return None


class LiquidationCriticalRule(BaseRule):
    rule_type = RuleType.LIQUIDATION
    severity = Severity.CRITICAL
    cooldown = timedelta(minutes=15)

    def evaluate(self, ctx: RuleContext) -> Alert | None:
        hf = ctx.get("health_factor")
        if hf is not None and hf < 1.1:
            return Alert(
                rule_type=self.rule_type,
                severity=self.severity,
                protocol=ctx["protocol"],
                chain=ctx["chain"],
                title="Liquidation Risk Critical",
                message=f"Health factor {hf:.2f} below critical threshold",
                details={"health_factor": hf},
                created_at=datetime.now(timezone.utc),
            )
        return None
