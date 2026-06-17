from datetime import date

from app.models import ReviewInputContext, RiskLevel, RuleResult


def run_tobacco_license_consistency_workflow(input_context: ReviewInputContext) -> dict:
    business_fields = _extract_fields(
        input_context.input.options.get("business_license_result"),
        input_context.input.options.get("business_license_fields"),
    )
    tobacco_fields = _extract_fields(
        input_context.input.options.get("tobacco_license_result"),
        input_context.input.options.get("tobacco_license_fields"),
    )
    rule_results = _review_rules(business_fields, tobacco_fields)
    failed = [rule for rule in rule_results if not rule.passed]
    comparison = {
        "business_license": business_fields,
        "tobacco_license": tobacco_fields,
        "differences": [
            {
                "rule_code": rule.rule_code,
                "field": rule.details.get("field"),
                "expected": rule.details.get("expected"),
                "actual": rule.details.get("actual"),
                "difference": rule.details.get("difference"),
            }
            for rule in failed
        ],
    }
    return {
        "input_context": input_context,
        "business_license_fields": business_fields,
        "tobacco_license_fields": tobacco_fields,
        "comparison": comparison,
        "rule_results": rule_results,
        "risk_level": _risk_level(failed),
        "needs_manual_review": bool(failed),
        "manual_review_reasons": [_manual_reason(rule) for rule in failed],
        "summary": (
            "营业执照与烟草证一致性校验通过"
            if not failed
            else "营业执照与烟草证存在需要人工复核的一致性问题"
        ),
        "source_evidence": {
            "supplier_name": input_context.input.supplier_name,
            "supplier_credit_code": input_context.input.supplier_credit_code,
            "declared_document_type": input_context.input.declared_document_type,
            "source": input_context.input.source,
            "options": input_context.input.options,
        },
    }


def _extract_fields(result_payload, explicit_fields) -> dict:
    if explicit_fields:
        return dict(explicit_fields)
    if not result_payload:
        return {}
    payload = (
        result_payload.model_dump(mode="json")
        if hasattr(result_payload, "model_dump")
        else dict(result_payload)
    )
    skill_result = payload.get("skill_result") if isinstance(payload, dict) else None
    if isinstance(skill_result, dict):
        fields = skill_result.get("normalized_fields") or skill_result.get("extracted_fields")
        if isinstance(fields, dict):
            return dict(fields)
    fields = payload.get("normalized_fields") or payload.get("extracted_fields")
    return dict(fields) if isinstance(fields, dict) else {}


def _review_rules(business_fields: dict, tobacco_fields: dict) -> list[RuleResult]:
    return [
        _type_rule("business_license", business_fields.get("document_type"), "营业执照类型"),
        _type_rule("tobacco_license", tobacco_fields.get("document_type"), "烟草证类型"),
        _same_field_rule(
            "BUSINESS_TOBACCO_SUBJECT_NAME_MATCH",
            "主体名称一致",
            "subject_name",
            business_fields.get("subject_name"),
            tobacco_fields.get("subject_name"),
        ),
        _same_field_rule(
            "BUSINESS_TOBACCO_ADDRESS_MATCH",
            "经营地址一致",
            "business_address",
            business_fields.get("business_address"),
            tobacco_fields.get("business_address"),
        ),
        _same_field_rule(
            "BUSINESS_TOBACCO_PERSON_MATCH",
            "法定代表人/负责人一致",
            "legal_person",
            business_fields.get("legal_person"),
            tobacco_fields.get("legal_person"),
        ),
        _tobacco_validity_rule(tobacco_fields.get("valid_to")),
    ]


def _type_rule(expected: str, actual: str | None, name: str) -> RuleResult:
    return RuleResult(
        rule_code=f"{expected.upper()}_TYPE_FOR_CONSISTENCY",
        rule_name=name,
        passed=actual == expected,
        risk_level_on_failure=RiskLevel.HIGH,
        message=f"{name}匹配" if actual == expected else f"{name}不匹配",
        details={
            "field": "document_type",
            "expected": expected,
            "actual": actual,
            "difference": None if actual == expected else "document_type_mismatch",
            "evidence": {"expected_source": "consistency_rule", "actual_source": actual},
        },
    )


def _same_field_rule(
    code: str,
    name: str,
    field: str,
    expected: str | None,
    actual: str | None,
) -> RuleResult:
    expected_norm = _normalize_text(expected)
    actual_norm = _normalize_text(actual)
    passed = bool(expected_norm) and expected_norm == actual_norm
    return RuleResult(
        rule_code=code,
        rule_name=name,
        passed=passed,
        risk_level_on_failure=RiskLevel.MEDIUM,
        message=f"{name}通过" if passed else f"{name}不通过",
        details={
            "field": field,
            "expected": expected,
            "actual": actual,
            "difference": None if passed else _difference(expected, actual),
            "evidence": {
                "expected_source": "business_license",
                "actual_source": "tobacco_license",
            },
        },
    )


def _tobacco_validity_rule(valid_to: str | None) -> RuleResult:
    if not valid_to:
        return RuleResult(
            rule_code="BUSINESS_TOBACCO_TOBACCO_VALIDITY",
            rule_name="烟草证有效期",
            passed=True,
            risk_level_on_failure=RiskLevel.MEDIUM,
            message="烟草证未识别截止日期，按长期有效处理",
            details={
                "field": "valid_to",
                "expected": "not_expired",
                "actual": valid_to,
                "difference": None,
                "evidence": {"actual_source": "tobacco_license"},
            },
        )
    try:
        days = (date.fromisoformat(valid_to) - date.today()).days
    except ValueError:
        return RuleResult(
            rule_code="BUSINESS_TOBACCO_TOBACCO_VALIDITY",
            rule_name="烟草证有效期",
            passed=False,
            risk_level_on_failure=RiskLevel.MEDIUM,
            message="烟草证有效期无法判断",
            details={
                "field": "valid_to",
                "expected": "valid_date",
                "actual": valid_to,
                "difference": "invalid_date",
                "evidence": {"actual_source": "tobacco_license"},
            },
        )
    passed = days >= 0
    return RuleResult(
        rule_code="BUSINESS_TOBACCO_TOBACCO_VALIDITY",
        rule_name="烟草证有效期",
        passed=passed,
        risk_level_on_failure=RiskLevel.HIGH,
        message="烟草证在有效期内" if passed else "烟草证已过期",
        details={
            "field": "valid_to",
            "expected": "not_expired",
            "actual": valid_to,
            "difference": None if passed else "expired",
            "days_until_expiry": days,
            "evidence": {"actual_source": "tobacco_license"},
        },
    )


def _risk_level(failed: list[RuleResult]) -> RiskLevel:
    if any(rule.risk_level_on_failure == RiskLevel.HIGH for rule in failed):
        return RiskLevel.HIGH
    if any(rule.risk_level_on_failure == RiskLevel.MEDIUM for rule in failed):
        return RiskLevel.MEDIUM
    return RiskLevel.NONE


def _manual_reason(rule: RuleResult) -> str:
    return f"{rule.rule_name}需要人工复核"


def _normalize_text(value: str | None) -> str:
    return "".join(str(value or "").split())


def _difference(expected: str | None, actual: str | None) -> str:
    if not expected:
        return "expected_missing"
    if not actual:
        return "actual_missing"
    return "value_mismatch"
