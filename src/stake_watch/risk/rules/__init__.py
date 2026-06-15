from stake_watch.risk.rules.liquidation import LiquidationWarningRule, LiquidationCriticalRule
from stake_watch.risk.rules.protocol_event import TvlCrashRule, CollectorFailureRule
from stake_watch.risk.rules.yield_change import ApySwingRule
from stake_watch.risk.rules.morpho import (
    MorphoUtilizationRule,
    MorphoWithdrawalRule,
    MorphoSharePriceRule,
    MorphoBadDebtRule,
    MorphoGovernanceRule,
)
from stake_watch.risk.rules.stablecoin import DepegWarningRule, DepegCriticalRule, SupplyChangeRule, StablecoinHardTriggerRule

def get_default_rules():
    return [
        LiquidationCriticalRule(),
        LiquidationWarningRule(),
        TvlCrashRule(),
        CollectorFailureRule(),
        ApySwingRule(),
        MorphoUtilizationRule(),
        MorphoWithdrawalRule(),
        MorphoSharePriceRule(),
        MorphoBadDebtRule(),
        MorphoGovernanceRule(),
        DepegCriticalRule(),
        DepegWarningRule(),
        SupplyChangeRule(),
        StablecoinHardTriggerRule(),
    ]
