from collections.abc import Iterable

from app.models import RiskLevel
from app.rules.context import RuleContext
from app.rules.protocol import Rule
from app.rules.result import RuleExecutionResult, RuleExecutionSummary, RuleStatus


class RuleExecutor:
    def __init__(self, rules: Iterable[Rule]) -> None:
        self._rules = list(rules)

    def run(self, context: RuleContext) -> RuleExecutionSummary:
        results = [self._evaluate(rule, context) for rule in self._rules]
        failed_risks = [
            result.risk_level_on_failure
            for result in results
            if result.status == RuleStatus.FAILED
        ]
        return RuleExecutionSummary(
            results=results,
            risk_level=_aggregate_risk(failed_risks),
            needs_manual_review=any(
                result.status == RuleStatus.ERROR for result in results
            ),
        )

    def _evaluate(self, rule: Rule, context: RuleContext) -> RuleExecutionResult:
        try:
            return rule.evaluate(context)
        except Exception as error:
            return RuleExecutionResult.error(rule=rule, error=error)


def _aggregate_risk(risks: list[RiskLevel]) -> RiskLevel:
    if RiskLevel.HIGH in risks:
        return RiskLevel.HIGH
    if RiskLevel.MEDIUM in risks:
        return RiskLevel.MEDIUM
    if RiskLevel.LOW in risks:
        return RiskLevel.LOW
    return RiskLevel.NONE
