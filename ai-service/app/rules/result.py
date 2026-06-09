from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.models import RiskLevel, RuleResult


class RuleStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"
    ERROR = "error"


@dataclass(frozen=True)
class RuleExecutionResult:
    rule_code: str
    rule_name: str
    status: RuleStatus
    risk_level_on_failure: RiskLevel
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def passed(
        cls,
        rule,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> "RuleExecutionResult":
        return cls.from_rule(
            rule=rule,
            status=RuleStatus.PASSED,
            message=message,
            details=details,
        )

    @classmethod
    def failed(
        cls,
        rule,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> "RuleExecutionResult":
        return cls.from_rule(
            rule=rule,
            status=RuleStatus.FAILED,
            message=message,
            details=details,
        )

    @classmethod
    def not_applicable(
        cls,
        rule,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> "RuleExecutionResult":
        return cls.from_rule(
            rule=rule,
            status=RuleStatus.NOT_APPLICABLE,
            message=message,
            details=details,
        )

    @classmethod
    def error(
        cls,
        rule,
        error: Exception,
    ) -> "RuleExecutionResult":
        return cls.from_rule(
            rule=rule,
            status=RuleStatus.ERROR,
            message=f"规则执行异常，需要人工复核：{rule.name}",
            details={"error_type": type(error).__name__},
        )

    @classmethod
    def from_rule(
        cls,
        rule,
        status: RuleStatus,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> "RuleExecutionResult":
        return cls(
            rule_code=rule.code,
            rule_name=rule.name,
            status=status,
            risk_level_on_failure=rule.risk_level_on_failure,
            message=message,
            details=details or {},
        )

    def to_rule_result(self) -> RuleResult:
        return RuleResult(
            rule_code=self.rule_code,
            rule_name=self.rule_name,
            passed=self.status in {
                RuleStatus.PASSED,
                RuleStatus.NOT_APPLICABLE,
            },
            risk_level_on_failure=self.risk_level_on_failure,
            message=self.message,
            details={
                **self.details,
                "status": self.status.value,
            },
        )


@dataclass(frozen=True)
class RuleExecutionSummary:
    results: list[RuleExecutionResult]
    risk_level: RiskLevel
    needs_manual_review: bool

    def to_rule_results(self) -> list[RuleResult]:
        return [result.to_rule_result() for result in self.results]
