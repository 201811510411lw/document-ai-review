from app.models import ReviewInput, ReviewInputContext, RiskLevel
from app.rules import (
    RuleContext,
    RuleExecutionResult,
    RuleExecutor,
    RuleStatus,
)


class PassingRule:
    code = "STUB_RULE_PASSED"
    name = "Stub rule passed"
    risk_level_on_failure = RiskLevel.HIGH

    def evaluate(self, context: RuleContext) -> RuleExecutionResult:
        return RuleExecutionResult.passed(
            rule=self,
            message=f"checked {context.input_context.task_id}",
        )


class FailingRule:
    code = "STUB_RULE_FAILED"
    name = "Stub rule failed"
    risk_level_on_failure = RiskLevel.MEDIUM

    def evaluate(self, context: RuleContext) -> RuleExecutionResult:
        return RuleExecutionResult.failed(
            rule=self,
            message="stub finding",
            details={"field": "supplier_name"},
        )


class NotApplicableRule:
    code = "STUB_RULE_NOT_APPLICABLE"
    name = "Stub rule not applicable"
    risk_level_on_failure = RiskLevel.HIGH

    def evaluate(self, context: RuleContext) -> RuleExecutionResult:
        return RuleExecutionResult.not_applicable(
            rule=self,
            message="document type does not require this rule",
        )


class ErrorRule:
    code = "STUB_RULE_ERROR"
    name = "Stub rule error"
    risk_level_on_failure = RiskLevel.HIGH

    def evaluate(self, context: RuleContext) -> RuleExecutionResult:
        raise RuntimeError("stub exploded")


class HighRiskFailingRule:
    code = "STUB_RULE_HIGH_FAILED"
    name = "Stub high risk rule failed"
    risk_level_on_failure = RiskLevel.HIGH

    def evaluate(self, context: RuleContext) -> RuleExecutionResult:
        return RuleExecutionResult.failed(rule=self, message="high risk finding")


def build_rule_context() -> RuleContext:
    input_context = ReviewInputContext(
        task_id="review-task-rules-001",
        input=ReviewInput(
            ocr_text="食品经营许可证",
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_license",
        ),
        skill_name="food_license",
        skill_version="v1",
        ruleset_version="food-license-rules-v1",
    )
    return RuleContext(
        input_context=input_context,
        facts={"document_type": "food_license"},
    )


def test_rule_executor_runs_passing_rule_and_maps_to_platform_rule_result():
    execution = RuleExecutor([PassingRule()]).run(build_rule_context())

    assert execution.risk_level == RiskLevel.NONE
    assert execution.needs_manual_review is False
    assert len(execution.results) == 1
    assert execution.results[0].status == RuleStatus.PASSED

    platform_results = execution.to_rule_results()

    assert len(platform_results) == 1
    assert platform_results[0].rule_code == "STUB_RULE_PASSED"
    assert platform_results[0].passed is True
    assert platform_results[0].risk_level_on_failure == RiskLevel.HIGH
    assert platform_results[0].message == "checked review-task-rules-001"


def test_rule_executor_aggregates_failed_rule_risk_and_maps_finding():
    execution = RuleExecutor([FailingRule()]).run(build_rule_context())

    assert execution.risk_level == RiskLevel.MEDIUM
    assert execution.needs_manual_review is False
    assert execution.results[0].status == RuleStatus.FAILED

    platform_result = execution.to_rule_results()[0]

    assert platform_result.rule_code == "STUB_RULE_FAILED"
    assert platform_result.passed is False
    assert platform_result.risk_level_on_failure == RiskLevel.MEDIUM
    assert platform_result.details == {
        "field": "supplier_name",
        "status": "failed",
    }


def test_rule_executor_does_not_raise_risk_for_not_applicable_rule():
    execution = RuleExecutor([NotApplicableRule()]).run(build_rule_context())

    assert execution.risk_level == RiskLevel.NONE
    assert execution.needs_manual_review is False
    assert execution.results[0].status == RuleStatus.NOT_APPLICABLE

    platform_result = execution.to_rule_results()[0]

    assert platform_result.passed is True
    assert platform_result.details["status"] == "not_applicable"


def test_rule_executor_converts_rule_exception_to_manual_review_finding():
    execution = RuleExecutor([ErrorRule()]).run(build_rule_context())

    assert execution.risk_level == RiskLevel.NONE
    assert execution.needs_manual_review is True
    assert execution.results[0].status == RuleStatus.ERROR

    platform_result = execution.to_rule_results()[0]

    assert platform_result.rule_code == "STUB_RULE_ERROR"
    assert platform_result.passed is False
    assert platform_result.details == {
        "error_type": "RuntimeError",
        "status": "error",
    }
    assert "规则执行异常" in platform_result.message


def test_rule_executor_aggregates_multiple_results_by_highest_failed_risk():
    execution = RuleExecutor(
        [
            PassingRule(),
            FailingRule(),
            NotApplicableRule(),
            ErrorRule(),
            HighRiskFailingRule(),
        ]
    ).run(build_rule_context())

    assert execution.risk_level == RiskLevel.HIGH
    assert execution.needs_manual_review is True
    assert [result.status for result in execution.results] == [
        RuleStatus.PASSED,
        RuleStatus.FAILED,
        RuleStatus.NOT_APPLICABLE,
        RuleStatus.ERROR,
        RuleStatus.FAILED,
    ]
