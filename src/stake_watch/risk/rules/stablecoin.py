from datetime import datetime, timedelta, timezone
from stake_watch.models.alert import Alert, Severity, RuleType
from stake_watch.risk.rules.base import BaseRule, RuleContext

class DepegWarningRule(BaseRule):
    """Deviation > 0.5% -> warning"""
    rule_type = RuleType.DEPEG
    severity = Severity.WARNING
    cooldown = timedelta(hours=1)
    def evaluate(self, ctx: RuleContext) -> Alert | None:
        deviation = ctx.get("stablecoin_deviation", 0)
        token = ctx.get("stablecoin_token", "")
        if 0.005 <= deviation < 0.01:
            return Alert(rule_type=self.rule_type, severity=self.severity,
                protocol=f"stablecoin_{token.lower()}", chain="multi",
                title=f"{token} Depeg Warning",
                message=f"{token} deviation {deviation:.2%} from $1.00",
                details={"token": token, "deviation": deviation},
                created_at=datetime.now(timezone.utc))
        return None

class DepegCriticalRule(BaseRule):
    """Deviation > 1% -> critical (immediate)"""
    rule_type = RuleType.DEPEG
    severity = Severity.CRITICAL
    cooldown = timedelta(minutes=15)
    def evaluate(self, ctx: RuleContext) -> Alert | None:
        deviation = ctx.get("stablecoin_deviation", 0)
        token = ctx.get("stablecoin_token", "")
        if deviation >= 0.01:
            return Alert(rule_type=self.rule_type, severity=self.severity,
                protocol=f"stablecoin_{token.lower()}", chain="multi",
                title=f"{token} Depeg Critical",
                message=f"{token} price ${ctx.get('stablecoin_price', 0):.4f} - deviation {deviation:.2%}",
                details={"token": token, "deviation": deviation, "price": ctx.get("stablecoin_price")},
                created_at=datetime.now(timezone.utc))
        return None

class SupplyChangeRule(BaseRule):
    """Net redemption > 3%/day -> warning, > 5% -> critical"""
    rule_type = RuleType.PROTOCOL_EVENT
    severity = Severity.WARNING
    cooldown = timedelta(hours=1)
    def evaluate(self, ctx: RuleContext) -> Alert | None:
        change = ctx.get("stablecoin_supply_change_24h_pct", 0)
        token = ctx.get("stablecoin_token", "")
        if change <= -5:
            return Alert(rule_type=self.rule_type, severity=Severity.CRITICAL,
                protocol=f"stablecoin_{token.lower()}", chain="multi",
                title=f"{token} Supply Crash",
                message=f"{token} supply dropped {abs(change):.1f}% in 24h",
                details={"token": token, "change_24h_pct": change},
                created_at=datetime.now(timezone.utc))
        if change <= -3:
            return Alert(rule_type=self.rule_type, severity=Severity.WARNING,
                protocol=f"stablecoin_{token.lower()}", chain="multi",
                title=f"{token} Supply Decline",
                message=f"{token} supply dropped {abs(change):.1f}% in 24h",
                details={"token": token, "change_24h_pct": change},
                created_at=datetime.now(timezone.utc))
        return None

class StablecoinHardTriggerRule(BaseRule):
    """Price < $0.98 -> immediate critical, bypasses all scoring"""
    rule_type = RuleType.DEPEG
    severity = Severity.CRITICAL
    cooldown = timedelta(minutes=5)
    def evaluate(self, ctx: RuleContext) -> Alert | None:
        price = ctx.get("stablecoin_price", 1.0)
        token = ctx.get("stablecoin_token", "")
        if price < 0.98:
            return Alert(rule_type=self.rule_type, severity=self.severity,
                protocol=f"stablecoin_{token.lower()}", chain="multi",
                title=f"{token} HARD TRIGGER: Price Below $0.98",
                message=f"{token} at ${price:.4f} - PRIORITIZE EXIT",
                details={"token": token, "price": price},
                created_at=datetime.now(timezone.utc))
        return None
