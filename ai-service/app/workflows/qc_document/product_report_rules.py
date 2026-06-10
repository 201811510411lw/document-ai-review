from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models import RiskLevel, ReviewStatus
from app.rules import RuleContext


PRODUCT_REPORT_RULE_CODES = (
    "PRODUCT_REPORT_TYPE_MATCH",
    "PRODUCT_REPORT_VENDOR_NAME_MATCH",
    "PRODUCT_REPORT_PRODUCT_NAME_PRESENT",
    "PRODUCT_REPORT_BATCH_OR_PRODUCTION_DATE_PRESENT",
    "PRODUCT_REPORT_CONCLUSION_PASS",
)


@dataclass(frozen=True)
class _RuleOutcome:
    rule_code: str
    rule_name: str
    passed: bool
    risk_level_on_failure: RiskLevel
    message: str
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_code": self.rule_code,
            "rule_name": self.rule_name,
            "passed": self.passed,
            "risk_level_on_failure": self.risk_level_on_failure.value,
            "message": self.message,
            "details": self.details,
        }


def evaluate_product_report_rules(
    *,
    declared_document_type: str,
    source_vendor_name: str,
    extracted_fields: dict,
) -> dict:
    normalized_fields = extracted_fields or {}
    outcomes = [
        _type_match_outcome(declared_document_type),
        _vendor_name_outcome(source_vendor_name, normalized_fields),
        _product_name_outcome(normalized_fields),
        _batch_or_production_date_outcome(normalized_fields),
        _conclusion_outcome(normalized_fields),
    ]
    failed_outcomes = [outcome for outcome in outcomes if not outcome.passed]
    risk_level = _aggregate_risk(failed_outcomes)
    needs_manual_review = bool(failed_outcomes)

    return {
        "rule_results": [outcome.as_dict() for outcome in outcomes],
        "risk_level": risk_level.value,
        "needs_manual_review": needs_manual_review,
        "status": (
            ReviewStatus.PENDING_MANUAL_REVIEW.value
            if needs_manual_review
            else ReviewStatus.REVIEWED.value
        ),
        "summary": _build_summary(risk_level, needs_manual_review),
        "manual_review_reasons": _manual_review_reasons(failed_outcomes),
    }


def run_product_report_default_rules(context: RuleContext) -> dict:
    facts = context.facts or {}
    normalized_fields = facts.get("normalized_fields") or {}
    if not isinstance(normalized_fields, dict):
        normalized_fields = {}
    return evaluate_product_report_rules(
        declared_document_type=_coalesce_text(
            facts.get("document_type"),
            context.input_context.input.declared_document_type,
            "product_report",
        ),
        source_vendor_name=_coalesce_text(
            facts.get("source_vendor_name"),
            context.input_context.input.supplier_name,
        ),
        extracted_fields=normalized_fields,
    )


def _type_match_outcome(declared_document_type: str) -> _RuleOutcome:
    passed = _normalize_text(declared_document_type) == "product_report"
    return _RuleOutcome(
        rule_code="PRODUCT_REPORT_TYPE_MATCH",
        rule_name="产品检验报告类型匹配",
        passed=passed,
        risk_level_on_failure=RiskLevel.HIGH,
        message=(
            "文档类型匹配产品检验报告"
            if passed
            else "文档类型与产品检验报告不匹配"
        ),
        details={
            "expected": "product_report",
            "actual": _normalize_text(declared_document_type),
        },
    )


def _vendor_name_outcome(
    source_vendor_name: str,
    extracted_fields: dict[str, Any],
) -> _RuleOutcome:
    extracted_vendor_name = _coalesce_text(extracted_fields.get("vendor_name"))
    source_vendor_name_normalized = _coalesce_text(source_vendor_name)
    if not extracted_vendor_name:
        return _RuleOutcome(
            rule_code="PRODUCT_REPORT_VENDOR_NAME_MATCH",
            rule_name="供应商名称匹配",
            passed=False,
            risk_level_on_failure=RiskLevel.MEDIUM,
            message="未识别到供应商名称",
            details={"field": "vendor_name", "actual": extracted_vendor_name},
        )
    passed = _normalize_text(extracted_vendor_name) == _normalize_text(
        source_vendor_name_normalized
    )
    return _RuleOutcome(
        rule_code="PRODUCT_REPORT_VENDOR_NAME_MATCH",
        rule_name="供应商名称匹配",
        passed=passed,
        risk_level_on_failure=RiskLevel.MEDIUM,
        message=(
            "供应商名称与来源信息一致"
            if passed
            else "供应商名称与来源信息不一致"
        ),
        details={
            "field": "vendor_name",
            "expected": source_vendor_name_normalized,
            "actual": extracted_vendor_name,
        },
    )


def _product_name_outcome(extracted_fields: dict[str, Any]) -> _RuleOutcome:
    product_name = _coalesce_text(extracted_fields.get("product_name"))
    passed = bool(product_name)
    return _RuleOutcome(
        rule_code="PRODUCT_REPORT_PRODUCT_NAME_PRESENT",
        rule_name="产品名存在",
        passed=passed,
        risk_level_on_failure=RiskLevel.MEDIUM,
        message=(
            "已识别到产品名称"
            if passed
            else "未识别到产品名称"
        ),
        details={"field": "product_name", "actual": product_name},
    )


def _batch_or_production_date_outcome(
    extracted_fields: dict[str, Any],
) -> _RuleOutcome:
    batch_number = _coalesce_text(extracted_fields.get("batch_number"))
    production_date = _coalesce_text(extracted_fields.get("production_date"))
    passed = bool(batch_number or production_date)
    return _RuleOutcome(
        rule_code="PRODUCT_REPORT_BATCH_OR_PRODUCTION_DATE_PRESENT",
        rule_name="批次或生产日期存在",
        passed=passed,
        risk_level_on_failure=RiskLevel.MEDIUM,
        message=(
            "已识别到批次号或生产日期"
            if passed
            else "未识别到批次号或生产日期"
        ),
        details={
            "field": "batch_number_or_production_date",
            "batch_number": batch_number,
            "production_date": production_date,
        },
    )


def _conclusion_outcome(extracted_fields: dict[str, Any]) -> _RuleOutcome:
    conclusion = _coalesce_text(extracted_fields.get("conclusion"))
    normalized_conclusion = _normalize_text(conclusion)
    positive_markers = ("合格", "通过", "符合")
    negative_markers = ("不合格", "不通过", "不符合")

    if any(marker in normalized_conclusion for marker in negative_markers):
        return _RuleOutcome(
            rule_code="PRODUCT_REPORT_CONCLUSION_PASS",
            rule_name="结论正向/负向/不明确",
            passed=False,
            risk_level_on_failure=RiskLevel.HIGH,
            message="检验结论明确为不合格",
            details={"conclusion": conclusion, "status": "negative"},
        )
    if any(marker in normalized_conclusion for marker in positive_markers):
        return _RuleOutcome(
            rule_code="PRODUCT_REPORT_CONCLUSION_PASS",
            rule_name="结论正向/负向/不明确",
            passed=True,
            risk_level_on_failure=RiskLevel.NONE,
            message="检验结论为正向",
            details={"conclusion": conclusion, "status": "positive"},
        )
    return _RuleOutcome(
        rule_code="PRODUCT_REPORT_CONCLUSION_PASS",
        rule_name="结论正向/负向/不明确",
        passed=False,
        risk_level_on_failure=RiskLevel.MEDIUM,
        message="检验结论不明确",
        details={"conclusion": conclusion, "status": "unclear"},
    )


def _aggregate_risk(failed_outcomes: list[_RuleOutcome]) -> RiskLevel:
    if any(outcome.risk_level_on_failure == RiskLevel.HIGH for outcome in failed_outcomes):
        return RiskLevel.HIGH
    if any(
        outcome.risk_level_on_failure == RiskLevel.MEDIUM
        for outcome in failed_outcomes
    ):
        return RiskLevel.MEDIUM
    if any(outcome.risk_level_on_failure == RiskLevel.LOW for outcome in failed_outcomes):
        return RiskLevel.LOW
    return RiskLevel.NONE


def _manual_review_reasons(failed_outcomes: list[_RuleOutcome]) -> list[str]:
    reasons: list[str] = []
    for outcome in failed_outcomes:
        reason = _reason_for_rule(outcome)
        if reason and reason not in reasons:
            reasons.append(reason)
    return reasons


def _reason_for_rule(outcome: _RuleOutcome) -> str:
    if outcome.rule_code == "PRODUCT_REPORT_TYPE_MATCH":
        return "文档类型不匹配"
    if outcome.rule_code == "PRODUCT_REPORT_VENDOR_NAME_MATCH":
        if outcome.details.get("actual"):
            return "供应商名称与来源信息不一致"
        return "供应商名称缺失"
    if outcome.rule_code == "PRODUCT_REPORT_PRODUCT_NAME_PRESENT":
        return "产品名缺失"
    if outcome.rule_code == "PRODUCT_REPORT_BATCH_OR_PRODUCTION_DATE_PRESENT":
        return "批次号或生产日期缺失"
    if outcome.rule_code == "PRODUCT_REPORT_CONCLUSION_PASS":
        status = outcome.details.get("status")
        if status == "negative":
            return "检验结论明确为不合格"
        if status == "unclear":
            return "检验结论不明确"
    return outcome.message


def _build_summary(risk_level: RiskLevel, needs_manual_review: bool) -> str:
    if not needs_manual_review:
        return "产品检验报告规则校验通过"
    if risk_level == RiskLevel.HIGH:
        return "产品检验报告存在高风险规则问题"
    if risk_level == RiskLevel.MEDIUM:
        return "产品检验报告存在需要人工复核的规则问题"
    if risk_level == RiskLevel.LOW:
        return "产品检验报告存在低风险规则问题"
    return "产品检验报告规则校验结果不明确"


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return "".join(str(value).split()).strip().lower()


def _coalesce_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""
