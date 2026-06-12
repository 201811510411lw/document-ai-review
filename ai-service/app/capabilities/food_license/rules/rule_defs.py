from datetime import date, datetime
import re
from typing import Any

from app.models import RiskLevel
from app.rules import RuleContext, RuleExecutionResult, RuleStatus


class FoodLicenseRuleEngineStubRule:
    code = "FOOD_LICENSE_RULE_ENGINE_STUB"
    name = "food_license 规则执行器接入占位规则"
    risk_level_on_failure = RiskLevel.LOW

    def evaluate(self, context: RuleContext) -> RuleExecutionResult:
        return RuleExecutionResult.passed(
            rule=self,
            message="food_license 已接入通用规则执行器。",
            details={"document_type": context.facts.get("document_type")},
        )


class FoodLicenseDocumentTypeRule:
    code = "FOOD_LICENSE_TYPE_MATCH"
    name = "证照类型是否为食品经营许可证"
    risk_level_on_failure = RiskLevel.HIGH

    def evaluate(self, context: RuleContext) -> RuleExecutionResult:
        document_type = context.facts.get("document_type")
        if not document_type:
            return _manual_review(
                self,
                "无法判断证照类型，需要人工复核。",
                field="document_type",
                actual=document_type,
            )
        if document_type != "food_license":
            return RuleExecutionResult.failed(
                rule=self,
                message="材料未识别为食品经营许可证。",
                details={
                    "field": "document_type",
                    "expected": "food_license",
                    "actual": document_type,
                },
            )
        return RuleExecutionResult.passed(
            rule=self,
            message="材料已识别为食品经营许可证。",
            details={
                "field": "document_type",
                "expected": "food_license",
                "actual": document_type,
            },
        )


class FoodLicenseSubjectNameMatchRule:
    code = "FOOD_LICENSE_SUBJECT_NAME_MATCH"
    name = "主体名称是否匹配供应商名称"
    risk_level_on_failure = RiskLevel.MEDIUM

    def evaluate(self, context: RuleContext) -> RuleExecutionResult:
        fields = _normalized_fields(context)
        actual = _get_field(fields, "subject_name")
        expected = context.input_context.input.supplier_name
        if not _has_text(actual):
            return _manual_review(
                self,
                "证照主体名称缺失，需要人工复核。",
                field="subject_name",
                expected=expected,
                actual=actual,
            )
        if not _has_text(expected):
            return _manual_review(
                self,
                "供应商名称缺失，需要人工复核。",
                field="supplier_name",
                expected=expected,
                actual=actual,
            )
        if _normalize_name(actual) != _normalize_name(expected):
            return RuleExecutionResult.failed(
                rule=self,
                message="证照主体名称与供应商名称不一致。",
                details={
                    "field": "subject_name",
                    "expected": expected,
                    "actual": actual,
                },
            )
        return RuleExecutionResult.passed(
            rule=self,
            message="证照主体名称与供应商名称一致。",
            details={
                "field": "subject_name",
                "expected": expected,
                "actual": actual,
            },
        )


class FoodLicenseCreditCodeMatchRule:
    code = "FOOD_LICENSE_CREDIT_CODE_MATCH"
    name = "统一社会信用代码是否匹配"
    risk_level_on_failure = RiskLevel.HIGH

    def evaluate(self, context: RuleContext) -> RuleExecutionResult:
        fields = _normalized_fields(context)
        actual = _get_field(fields, "credit_code")
        expected = context.input_context.input.supplier_credit_code
        if not _has_text(actual):
            return _manual_review(
                self,
                "证照统一社会信用代码缺失，需要人工复核。",
                field="credit_code",
                expected=expected,
                actual=actual,
            )
        if not _has_text(expected):
            return _manual_review(
                self,
                "供应商统一社会信用代码缺失，需要人工复核。",
                field="supplier_credit_code",
                expected=expected,
                actual=actual,
            )
        if _normalize_credit_code(actual) != _normalize_credit_code(expected):
            return RuleExecutionResult.failed(
                rule=self,
                message="证照统一社会信用代码与供应商信用代码不一致。",
                details={
                    "field": "credit_code",
                    "expected": expected,
                    "actual": actual,
                },
            )
        return RuleExecutionResult.passed(
            rule=self,
            message="证照统一社会信用代码与供应商信用代码一致。",
            details={
                "field": "credit_code",
                "expected": expected,
                "actual": actual,
            },
        )


class FoodLicenseValidityRule:
    code = "FOOD_LICENSE_VALIDITY_PERIOD"
    name = "有效期是否过期或三十天内临期"
    risk_level_on_failure = RiskLevel.HIGH
    warning_risk_level = RiskLevel.MEDIUM
    expiring_days_threshold = 30

    def evaluate(self, context: RuleContext) -> RuleExecutionResult:
        fields = _normalized_fields(context)
        actual = _get_field(fields, "valid_to")
        if not _has_text(actual):
            return RuleExecutionResult.passed(
                rule=self,
                message="证照未识别到有效期，按长期有效处理。",
                details={
                    "field": "valid_to",
                    "actual": actual,
                    "assumed_long_term": True,
                },
            )

        valid_to = _parse_date(str(actual))
        if valid_to is None:
            return _manual_review(
                self,
                "证照有效期截止日期无法解析，需要人工复核。",
                field="valid_to",
                actual=actual,
            )

        current_date = _current_date(context)
        days_until_expiry = (valid_to - current_date).days
        details = {
            "field": "valid_to",
            "actual": actual,
            "current_date": current_date.isoformat(),
            "valid_to": valid_to.isoformat(),
            "days_until_expiry": days_until_expiry,
            "expiring_days_threshold": self.expiring_days_threshold,
        }
        if days_until_expiry < 0:
            return RuleExecutionResult.failed(
                rule=self,
                message="证照已过期。",
                details=details,
            )
        if days_until_expiry <= self.expiring_days_threshold:
            return RuleExecutionResult(
                rule_code=self.code,
                rule_name=self.name,
                status=RuleStatus.FAILED,
                risk_level_on_failure=self.warning_risk_level,
                message="证照将在三十天内到期。",
                details=details,
            )
        return RuleExecutionResult.passed(
            rule=self,
            message="证照有效期未过期且未在三十天内到期。",
            details=details,
        )


def build_food_license_rules():
    return [
        FoodLicenseRuleEngineStubRule(),
        FoodLicenseDocumentTypeRule(),
        FoodLicenseSubjectNameMatchRule(),
        FoodLicenseCreditCodeMatchRule(),
        FoodLicenseValidityRule(),
    ]


def _manual_review(
    rule,
    message: str,
    *,
    field: str,
    expected: Any = None,
    actual: Any = None,
) -> RuleExecutionResult:
    return RuleExecutionResult.from_rule(
        rule=rule,
        status=RuleStatus.ERROR,
        message=message,
        details={
            "field": field,
            "expected": expected,
            "actual": actual,
            "reason": "missing_or_unreadable_field",
        },
    )


def _normalized_fields(context: RuleContext) -> Any:
    return context.facts.get("normalized_fields") or context.facts.get(
        "extracted_fields",
    )


def _get_field(fields: Any, field_name: str) -> Any:
    if fields is None:
        return None
    if isinstance(fields, dict):
        return fields.get(field_name)
    return getattr(fields, field_name, None)


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", value).strip()


def _normalize_credit_code(value: str) -> str:
    return re.sub(r"\s+", "", value).strip().upper()


def _parse_date(value: str) -> date | None:
    match = re.search(
        r"(\d{4})\s*(?:年|-|\.)\s*(\d{1,2})\s*(?:月|-|\.)\s*(\d{1,2})",
        value,
    )
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _current_date(context: RuleContext) -> date:
    value = context.facts.get("current_date")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return date.today()
    return date.today()
