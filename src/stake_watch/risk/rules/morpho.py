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


class MorphoBadDebtRule(BaseRule):
    """Potential bad debt at -20% > 1% of vault assets → warning, > 3% → critical"""

    rule_type = RuleType.MORPHO
    severity = Severity.WARNING
    cooldown = timedelta(hours=1)

    def evaluate(self, ctx: RuleContext) -> Alert | None:
        pct = ctx.get("worst_case_bad_debt_pct", 0)
        if pct > 0.03:
            return Alert(
                rule_type=self.rule_type,
                severity=Severity.CRITICAL,
                protocol=ctx["protocol"],
                chain=ctx["chain"],
                title="Morpho Bad Debt Critical",
                message=f"Potential bad debt at -20%: {pct:.1%} of vault assets",
                details={"worst_case_bad_debt_pct": pct},
                created_at=datetime.now(timezone.utc),
            )
        if pct > 0.01:
            return Alert(
                rule_type=self.rule_type,
                severity=Severity.WARNING,
                protocol=ctx["protocol"],
                chain=ctx["chain"],
                title="Morpho Bad Debt Warning",
                message=f"Potential bad debt at -20%: {pct:.1%} of vault assets",
                details={"worst_case_bad_debt_pct": pct},
                created_at=datetime.now(timezone.utc),
            )
        return None


class MorphoGovernanceRule(BaseRule):
    """Governance changes detected → info, critical changes → critical"""

    rule_type = RuleType.MORPHO
    severity = Severity.INFO
    cooldown = timedelta(hours=6)
    CRITICAL_EVENTS = {"SetCurator", "SetGuardian"}

    def evaluate(self, ctx: RuleContext) -> Alert | None:
        events = ctx.get("governance_events", [])
        if not events:
            return None
        critical = [e for e in events if e.get("event_type") in self.CRITICAL_EVENTS]
        if critical:
            return Alert(
                rule_type=self.rule_type,
                severity=Severity.CRITICAL,
                protocol=ctx["protocol"],
                chain=ctx["chain"],
                title="Morpho Critical Governance Change",
                message=f"Detected: {', '.join(e['event_type'] for e in critical)}",
                details={"events": critical},
                created_at=datetime.now(timezone.utc),
            )
        return Alert(
            rule_type=self.rule_type,
            severity=Severity.INFO,
            protocol=ctx["protocol"],
            chain=ctx["chain"],
            title="Morpho Governance Event",
            message=f"Detected: {', '.join(e.get('event_type', '?') for e in events)}",
            details={"events": events},
            created_at=datetime.now(timezone.utc),
        )
