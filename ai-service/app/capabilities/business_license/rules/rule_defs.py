from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.models import RiskLevel, RuleResult


@dataclass(frozen=True)
class _Outcome:
    rule_code: str
    rule_name: str
    passed: bool
    risk_level_on_failure: RiskLevel
    message: str
    details: dict[str, Any]
    manual_review_reason: str | None = None

    def to_rule_result(self) -> RuleResult:
        return RuleResult(
            rule_code=self.rule_code,
            rule_name=self.rule_name,
            passed=self.passed,
            risk_level_on_failure=self.risk_level_on_failure,
            message=self.message,
            details=self.details,
        )


def evaluate_business_license_rules(
    *,
    document_type: str | None,
    source_subject_name: str,
    source_credit_code: str,
    extracted_fields: dict[str, Any],
    current_date: date | None = None,
) -> dict[str, Any]:
    fields = extracted_fields or {}
    today = current_date or date.today()
    outcomes = [
        _document_type_outcome(document_type),
        _subject_name_outcome(source_subject_name, fields),
        _credit_code_outcome(source_credit_code, fields),
        _validity_outcome(fields, today),
        _required_fields_outcome(fields),
    ]
    failed = [outcome for outcome in outcomes if not outcome.passed]
    risk_level = _aggregate_risk(failed)
    return {
        "rule_results": [outcome.to_rule_result() for outcome in outcomes],
        "risk_level": risk_level,
        "needs_manual_review": bool(failed),
        "manual_review_reasons": [
            outcome.manual_review_reason or outcome.message for outcome in failed
        ],
    }


def _document_type_outcome(document_type: str | None) -> _Outcome:
    passed = document_type == "business_license"
    return _Outcome(
        "BUSINESS_LICENSE_TYPE_MATCH",
        "营业执照类型匹配",
        passed,
        RiskLevel.HIGH,
        "文档类型匹配营业执照" if passed else "文档类型不匹配营业执照",
        {"expected": "business_license", "actual": document_type},
        None if passed else "文档类型不匹配",
    )


def _subject_name_outcome(source_subject_name: str, fields: dict[str, Any]) -> _Outcome:
    actual = _normalize_text(fields.get("subject_name"))
    expected = _normalize_text(source_subject_name)
    passed = bool(actual and expected and actual == expected)
    missing = not actual or not expected
    return _Outcome(
        "BUSINESS_LICENSE_SUBJECT_NAME_MATCH",
        "营业执照主体名称匹配",
        passed,
        RiskLevel.MEDIUM,
        "营业执照主体名称与来源一致" if passed else "营业执照主体名称与来源不一致或缺失",
        {"field": "subject_name", "expected": source_subject_name, "actual": fields.get("subject_name")},
        "主体名称缺失" if missing else "主体名称与来源信息不一致",
    )


def _credit_code_outcome(source_credit_code: str, fields: dict[str, Any]) -> _Outcome:
    actual = _normalize_text(fields.get("credit_code")).upper()
    expected = _normalize_text(source_credit_code).upper()
    valid_shape = bool(actual) and len(actual) in {15, 18}
    passed = bool(actual and expected and actual == expected and valid_shape)
    if not actual:
        reason = "统一社会信用代码缺失"
    elif not valid_shape:
        reason = "统一社会信用代码格式异常"
    else:
        reason = "统一社会信用代码与来源信息不一致"
    return _Outcome(
        "BUSINESS_LICENSE_CREDIT_CODE_MATCH",
        "统一社会信用代码匹配",
        passed,
        RiskLevel.HIGH,
        "统一社会信用代码与来源一致" if passed else "统一社会信用代码异常或不一致",
        {"field": "credit_code", "expected": source_credit_code, "actual": fields.get("credit_code")},
        None if passed else reason,
    )


def _validity_outcome(fields: dict[str, Any], today: date) -> _Outcome:
    valid_to = fields.get("valid_to")
    if not _normalize_text(valid_to):
        return _Outcome(
            "BUSINESS_LICENSE_VALIDITY_PERIOD",
            "营业执照有效期",
            True,
            RiskLevel.HIGH,
            "营业执照未识别到有效期，按长期有效处理",
            {"valid_to": valid_to, "assumed_long_term": True},
        )
    if valid_to == "长期":
        return _Outcome(
            "BUSINESS_LICENSE_VALIDITY_PERIOD",
            "营业执照有效期",
            True,
            RiskLevel.HIGH,
            "营业执照长期有效",
            {"valid_to": valid_to},
        )
    parsed_valid_to = _parse_iso_date(valid_to)
    if parsed_valid_to is None:
        return _Outcome(
            "BUSINESS_LICENSE_VALIDITY_PERIOD",
            "营业执照有效期",
            False,
            RiskLevel.MEDIUM,
            "营业执照有效期无法判断",
            {"valid_to": valid_to},
            "有效期无法判断",
        )
    expired = parsed_valid_to < today
    expiring_soon = 0 <= (parsed_valid_to - today).days <= 30
    passed = not expired and not expiring_soon
    return _Outcome(
        "BUSINESS_LICENSE_VALIDITY_PERIOD",
        "营业执照有效期",
        passed,
        RiskLevel.HIGH if expired else RiskLevel.MEDIUM,
        "营业执照在有效期内" if passed else "营业执照已过期或临近过期",
        {"valid_to": valid_to, "current_date": today.isoformat()},
        "营业执照已过期" if expired else "营业执照临近过期",
    )


def _required_fields_outcome(fields: dict[str, Any]) -> _Outcome:
    missing = [
        field_name
        for field_name in ("subject_name", "credit_code")
        if not fields.get(field_name)
    ]
    passed = not missing
    return _Outcome(
        "BUSINESS_LICENSE_REQUIRED_FIELDS_PRESENT",
        "营业执照关键字段完整",
        passed,
        RiskLevel.MEDIUM,
        "营业执照关键字段完整" if passed else "营业执照缺少可审核关键字段",
        {"missing_fields": missing},
        None if passed else "关键字段缺失",
    )


def _aggregate_risk(failed_outcomes: list[_Outcome]) -> RiskLevel:
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


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return "".join(str(value).split()).strip()


def _parse_iso_date(value: Any) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
