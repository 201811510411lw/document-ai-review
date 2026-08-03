import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import ReviewStatus, RiskLevel, RuleResult


_PRODUCT_NAME_RULE_CODES = {
    "PRODUCT_REPORT_PRODUCT_NAME_PRESENT",
    "PRODUCT_REPORT_PRODUCT_NAME_MATCH",
}
_PACKAGE_SPEC_PATTERN = re.compile(
    r"(?:净含量\s*[:：]?)?\d+(?:\.\d+)?\s*"
    r"(?:kg|mg|ml|g|l|千克|毫升|克|升)"
    r"(?:\s*[*x×]\s*\d+\s*(?:袋|盒|瓶|罐|包|支|听|个|杯))?",
    flags=re.IGNORECASE,
)
_EXPLICIT_BRAND_PATTERN = re.compile(
    r"^(?:【[^】]+】|\[[^\]]+\]|[^，,。:：\s]{1,12}牌)"
)


class RuleReviewResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: ReviewStatus
    risk_level: RiskLevel
    needs_manual_review: bool
    summary: str
    manual_review_reasons: list[str] = Field(default_factory=list)
    rule_results: list[RuleResult] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def apply_product_name_rules(
    rules_result: dict[str, Any],
    *,
    expected: str | None,
    actual: str | None,
) -> RuleReviewResult:
    result = RuleReviewResult.model_validate(rules_result)
    deterministic_rules = [_product_name_present_rule(actual)]
    if expected:
        deterministic_rules.append(_product_name_match_rule(expected, actual))

    retained_rules = [
        rule
        for rule in result.rule_results
        if rule.rule_code not in _PRODUCT_NAME_RULE_CODES
    ]
    if result.metadata.get("implementation_status") == "failed":
        retained_rules.append(_skill_rule_review_completed_rule(result.metadata))
    all_rules = [*retained_rules, *deterministic_rules]
    failed_rules = [rule for rule in all_rules if not rule.passed]
    risk_level = _aggregate_risk_level(failed_rules)
    status = (
        ReviewStatus.FAILED
        if risk_level == RiskLevel.HIGH
        else ReviewStatus.PENDING_MANUAL_REVIEW
        if failed_rules
        else ReviewStatus.REVIEWED
    )

    retained_reasons = [
        reason
        for reason in result.manual_review_reasons
        if not _is_product_name_reason(reason)
    ]
    product_name_reasons = [
        _product_name_failure_reason(rule)
        for rule in deterministic_rules
        if not rule.passed
    ]
    manual_review_reasons = list(
        dict.fromkeys([*retained_reasons, *product_name_reasons])
    )
    return result.model_copy(
        update={
            "status": status,
            "risk_level": risk_level,
            "needs_manual_review": bool(failed_rules) and risk_level != RiskLevel.HIGH,
            "summary": _summary(risk_level, bool(failed_rules)),
            "manual_review_reasons": manual_review_reasons,
            "rule_results": all_rules,
        }
    )


def _product_name_present_rule(actual: str | None) -> RuleResult:
    return RuleResult(
        rule_code="PRODUCT_REPORT_PRODUCT_NAME_PRESENT",
        rule_name="产品名称存在",
        passed=bool(actual),
        risk_level_on_failure=RiskLevel.MEDIUM,
        message="已识别产品名称" if actual else "产品名称缺失",
        details={"field": "product_name", "actual": actual},
    )


def _product_name_match_rule(expected: str, actual: str | None) -> RuleResult:
    expected_core = _normalize_product_name(expected)
    actual_core = _normalize_product_name(actual or "")
    passed = bool(actual_core) and actual_core == expected_core
    return RuleResult(
        rule_code="PRODUCT_REPORT_PRODUCT_NAME_MATCH",
        rule_name="产品名称与来源商品名称匹配",
        passed=passed,
        risk_level_on_failure=RiskLevel.MEDIUM,
        message="产品名称与来源商品名称一致" if passed else "产品名称与来源商品名称不一致",
        details={
            "field": "product_name",
            "expected": expected,
            "actual": actual,
            "expected_core": expected_core,
            "actual_core": actual_core,
            "match_reason": (
                "剔除显式品牌、规格包装、括号限定词和标点后核心品名一致"
                if passed
                else "归一化后的核心品名不一致"
            ),
            "confidence": "HIGH" if passed else "LOW",
        },
    )


def _skill_rule_review_completed_rule(metadata: dict[str, Any]) -> RuleResult:
    return RuleResult(
        rule_code="PRODUCT_REPORT_SKILL_RULE_REVIEW_COMPLETED",
        rule_name="产品报告规则审核执行完成",
        passed=False,
        risk_level_on_failure=RiskLevel.MEDIUM,
        message="Skill 规则审核未完成",
        details={"error_code": metadata.get("error_code")},
    )


def _normalize_product_name(value: str) -> str:
    without_brand = _EXPLICIT_BRAND_PATTERN.sub("", value.strip())
    without_qualifiers = re.sub(r"(?:\([^)]*\)|（[^）]*）)", "", without_brand)
    without_package_spec = _PACKAGE_SPEC_PATTERN.sub("", without_qualifiers)
    return re.sub(r"[\W_]", "", without_package_spec, flags=re.UNICODE).lower()


def _aggregate_risk_level(failed_rules: list[RuleResult]) -> RiskLevel:
    for risk_level in (RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW):
        if any(rule.risk_level_on_failure == risk_level for rule in failed_rules):
            return risk_level
    return RiskLevel.NONE


def _is_product_name_reason(reason: str) -> bool:
    return any(token in reason for token in ("产品名", "产品名称", "商品名称", "样品名称"))


def _product_name_failure_reason(rule: RuleResult) -> str:
    if rule.rule_code == "PRODUCT_REPORT_PRODUCT_NAME_PRESENT":
        return "产品名缺失"
    return "产品名称与来源商品名称不一致"


def _summary(risk_level: RiskLevel, has_failures: bool) -> str:
    if not has_failures:
        return "产品检验报告规则校验通过"
    if risk_level == RiskLevel.HIGH:
        return "产品检验报告存在高风险规则问题"
    return "产品检验报告存在需要人工复核的规则问题"
