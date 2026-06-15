from datetime import datetime, timedelta, timezone
from stake_watch.models.alert import Alert, Severity, RuleType
from stake_watch.risk.rules.base import BaseRule, RuleContext


class MorphoUtilizationRule(BaseRule):
    rule_type = RuleType.MORPHO
    severity = Severity.WARNING
    cooldown = timedelta(hours=1)

    def evaluate(self, ctx: RuleContext) -> Alert | None:
        util = ctx.get("max_utilization", 0)
        if util > 0.92:
            return Alert(
                rule_type=self.rule_type,
                severity=self.severity,
                protocol=ctx["protocol"],
                chain=ctx["chain"],
                title="Morpho High Utilization",
                message=f"Market utilization {util:.0%}",
                details={"max_utilization": util},
                created_at=datetime.now(timezone.utc),
            )
        return None


class MorphoWithdrawalRule(BaseRule):
    rule_type = RuleType.MORPHO
    severity = Severity.CRITICAL
    cooldown = timedelta(minutes=15)

    def evaluate(self, ctx: RuleContext) -> Alert | None:
        if ctx.get("can_withdraw_10pct") is False:
            return Alert(
                rule_type=self.rule_type,
                severity=self.severity,
                protocol=ctx["protocol"],
                chain=ctx["chain"],
                title="Withdrawal Blocked",
                message=f"Cannot withdraw 10%. Liquidity ratio: {ctx.get('liquidity_ratio', 0):.2f}",
                details={"liquidity_ratio": ctx.get("liquidity_ratio")},
                created_at=datetime.now(timezone.utc),
            )
        return None


class MorphoSharePriceRule(BaseRule):
    rule_type = RuleType.MORPHO
    severity = Severity.CRITICAL
    cooldown = timedelta(minutes=15)

    def evaluate(self, ctx: RuleContext) -> Alert | None:
        change = ctx.get("share_price_change", 0)
        if change < 0:
            return Alert(
                rule_type=self.rule_type,
                severity=self.severity,
                protocol=ctx["protocol"],
                chain=ctx["chain"],
                title="Share Price Decrease",
                message=f"Vault share price decreased by {abs(change):.4f}",
                details={"share_price_change": change},
                created_at=datetime.now(timezone.utc),
            )
        return None
