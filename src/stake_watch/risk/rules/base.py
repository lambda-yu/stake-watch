from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import timedelta
from stake_watch.models.alert import Alert, Severity, RuleType

RuleContext = dict

class BaseRule(ABC):
    rule_type: RuleType
    severity: Severity
    cooldown: timedelta
    @abstractmethod
    def evaluate(self, context: RuleContext) -> Alert | None: ...
