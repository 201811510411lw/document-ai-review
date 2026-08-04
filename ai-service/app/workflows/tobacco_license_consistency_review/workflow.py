import re
import unicodedata
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
    review_mode = str(input_context.input.options.get("review_mode") or "standard")
    store_in_store = dict(input_context.input.options.get("store_in_store") or {})
    rule_results = _review_rules(
        business_fields,
        tobacco_fields,
        review_mode=review_mode,
        store_in_store=store_in_store,
        business_result=input_context.input.options.get("business_license_result"),
        tobacco_result=input_context.input.options.get("tobacco_license_result"),
    )
    failed = [rule for rule in rule_results if not rule.passed]
    comparison = {
        "business_license": business_fields,
        "tobacco_license": tobacco_fields,
        "review_mode": review_mode,
        "store_in_store": store_in_store if review_mode == "store_in_store" else {},
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
            ("店中店营业执照与烟草证证据链校验通过" if review_mode == "store_in_store" else "营业执照与烟草证一致性校验通过")
            if not failed
            else ("店中店证据链存在需要人工复核的问题" if review_mode == "store_in_store" else "营业执照与烟草证存在需要人工复核的一致性问题")
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


def _review_rules(
    business_fields: dict,
    tobacco_fields: dict,
    *,
    review_mode: str,
    store_in_store: dict,
    business_result=None,
    tobacco_result=None,
) -> list[RuleResult]:
    rules = [
        _child_review_ready_rule("BUSINESS_LICENSE", "营业执照", business_result),
        _child_review_ready_rule("TOBACCO_LICENSE", "烟草证", tobacco_result),
        _type_rule("business_license", business_fields.get("document_type"), "营业执照类型"),
        _type_rule("tobacco_license", tobacco_fields.get("document_type"), "烟草证类型"),
        _required_field_rule(
            "TOBACCO_LICENSE_NO_FOR_CONSISTENCY",
            "烟草证许可证号完整",
            "license_no",
            tobacco_fields.get("license_no"),
        ),
        _evidence_rule(
            "BUSINESS_LICENSE_EVIDENCE_FOR_CONSISTENCY",
            "营业执照关键字段证据完整",
            business_fields,
            ("subject_name", "business_address", "legal_person"),
        ),
        _evidence_rule(
            "TOBACCO_LICENSE_EVIDENCE_FOR_CONSISTENCY",
            "烟草证关键字段证据完整",
            tobacco_fields,
            ("subject_name", "business_address", "legal_person", "license_no", "valid_to"),
        ),
    ]
    if review_mode == "store_in_store":
        rules.extend(_store_in_store_rules(business_fields, tobacco_fields, store_in_store))
    else:
        rules.extend([
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
        ])
    rules.append(_tobacco_validity_rule(tobacco_fields.get("valid_to")))
    return rules


def _store_in_store_rules(
    holder_fields: dict,
    tobacco_fields: dict,
    store_in_store: dict,
) -> list[RuleResult]:
    relationship = dict(store_in_store.get("relationship_evidence") or {})
    multi_address = dict(store_in_store.get("multi_address_evidence") or {})
    franchisee = dict(store_in_store.get("franchisee_business_license_fields") or {})
    tobacco_address = tobacco_fields.get("business_address")
    holder_address = holder_fields.get("business_address")
    listed_addresses = multi_address.get("addresses") or []
    multi_address_matches_holder = _normalized_equal(
        multi_address.get("holder_name"), tobacco_fields.get("subject_name")
    )
    address_covered = _normalized_equal(holder_address, tobacco_address) or (
        multi_address_matches_holder
        and any(_normalized_equal(address, tobacco_address) for address in listed_addresses)
    )
    relationship_complete = bool(
        relationship.get("document_id")
        and relationship.get("franchisee_name")
        and relationship.get("holder_name")
        and relationship.get("address")
    )
    relationship_matches = (
        relationship_complete
        and _normalized_equal(relationship.get("holder_name"), tobacco_fields.get("subject_name"))
        and _normalized_equal(relationship.get("address"), tobacco_address)
        and (not franchisee.get("subject_name") or _normalized_equal(relationship.get("franchisee_name"), franchisee.get("subject_name")))
    )
    return [
        _same_field_rule(
            "STORE_IN_STORE_HOLDER_NAME_MATCH",
            "持证主体名称一致",
            "subject_name",
            holder_fields.get("subject_name"),
            tobacco_fields.get("subject_name"),
        ),
        _optional_same_field_rule(
            "STORE_IN_STORE_HOLDER_PERSON_MATCH",
            "持证主体负责人一致",
            "legal_person",
            holder_fields.get("legal_person"),
            tobacco_fields.get("legal_person"),
        ),
        _rule_result(
            "STORE_IN_STORE_RELATIONSHIP_EVIDENCE",
            "加盟/联营/场地授权凭证",
            relationship_matches,
            "relationship_evidence_missing_or_mismatch",
            {"relationship_evidence": relationship, "franchisee": franchisee},
        ),
        _rule_result(
            "STORE_IN_STORE_ADDRESS_COVERAGE",
            "持证经营地址覆盖",
            address_covered,
            "address_not_registered_or_listed",
            {"holder_address": holder_address, "tobacco_address": tobacco_address, "multi_address_evidence": multi_address},
        ),
    ]


def _child_review_ready_rule(code_prefix: str, name: str, result_payload) -> RuleResult:
    if result_payload is None:
        return RuleResult(
            rule_code=f"{code_prefix}_CHILD_REVIEW_READY",
            rule_name=f"{name}子审核就绪",
            passed=True,
            risk_level_on_failure=RiskLevel.MEDIUM,
            message=f"{name}使用显式确认字段",
            details={"source": "explicit_fields"},
        )
    payload = (
        result_payload.model_dump(mode="json")
        if hasattr(result_payload, "model_dump")
        else dict(result_payload)
    )
    status = str(payload.get("status") or "")
    needs_manual_review = bool(payload.get("needs_manual_review", False))
    passed = status == "REVIEWED" and not needs_manual_review
    return RuleResult(
        rule_code=f"{code_prefix}_CHILD_REVIEW_READY",
        rule_name=f"{name}子审核就绪",
        passed=passed,
        risk_level_on_failure=RiskLevel.MEDIUM,
        message=f"{name}子审核已完成" if passed else f"{name}子审核未形成可靠自动结论",
        details={
            "status": status or None,
            "needs_manual_review": needs_manual_review,
            "difference": None if passed else "child_review_not_ready",
            "technical_error": status == "FAILED",
        },
    )


def _required_field_rule(code: str, name: str, field: str, value) -> RuleResult:
    passed = bool(_normalize_text(value))
    return RuleResult(
        rule_code=code,
        rule_name=name,
        passed=passed,
        risk_level_on_failure=RiskLevel.MEDIUM,
        message=f"{name}通过" if passed else f"{name}缺失",
        details={
            "field": field,
            "actual": value,
            "difference": None if passed else "actual_missing",
        },
    )


def _evidence_rule(
    code: str,
    name: str,
    fields: dict,
    required_fields: tuple[str, ...],
) -> RuleResult:
    required_evidence_fields = [f"{field}_evidence" for field in required_fields]
    missing = [
        evidence_field
        for evidence_field in required_evidence_fields
        if not _normalize_text(fields.get(evidence_field))
    ]
    return RuleResult(
        rule_code=code,
        rule_name=name,
        passed=not missing,
        risk_level_on_failure=RiskLevel.MEDIUM,
        message=f"{name}通过" if not missing else f"{name}不足",
        details={
            "required_evidence_fields": required_evidence_fields,
            "missing_evidence_fields": missing,
            "difference": None if not missing else "evidence_missing",
        },
    )


def _optional_same_field_rule(code: str, name: str, field: str, expected: str | None, actual: str | None) -> RuleResult:
    if not _normalize_text(expected) or not _normalize_text(actual):
        return RuleResult(rule_code=code, rule_name=name, passed=True, risk_level_on_failure=RiskLevel.MEDIUM, message=f"{name}未完整识别，需结合其他证据复核", details={"field": field, "expected": expected, "actual": actual, "evidence": {}})
    return _same_field_rule(code, name, field, expected, actual)


def _rule_result(code: str, name: str, passed: bool, difference: str, details: dict) -> RuleResult:
    return RuleResult(rule_code=code, rule_name=name, passed=passed, risk_level_on_failure=RiskLevel.MEDIUM, message=f"{name}通过" if passed else f"{name}不通过", details={"difference": None if passed else difference, **details})


def _normalized_equal(left: str | None, right: str | None) -> bool:
    return bool(_normalize_text(left)) and _normalize_text(left) == _normalize_text(right)


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
    expected_norm = _normalize_comparison_value(field, expected)
    actual_norm = _normalize_comparison_value(field, actual)
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
            passed=False,
            risk_level_on_failure=RiskLevel.MEDIUM,
            message="烟草证未识别截止日期，无法自动判断有效期",
            details={
                "field": "valid_to",
                "expected": "not_expired",
                "actual": valid_to,
                "difference": "actual_missing",
                "evidence": {"actual_source": "tobacco_license"},
            },
        )
    normalized_valid_to = _normalize_date_value(valid_to)
    try:
        days = (date.fromisoformat(normalized_valid_to) - date.today()).days
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
    passed = days > 30
    if days < 0:
        risk_level = RiskLevel.HIGH
        message = "烟草证已过期"
        difference = "expired"
    elif days <= 30:
        risk_level = RiskLevel.MEDIUM
        message = "烟草证三十天内到期"
        difference = "expiring_soon"
    else:
        risk_level = RiskLevel.HIGH
        message = "烟草证在有效期内"
        difference = None
    return RuleResult(
        rule_code="BUSINESS_TOBACCO_TOBACCO_VALIDITY",
        rule_name="烟草证有效期",
        passed=passed,
        risk_level_on_failure=risk_level,
        message=message,
        details={
            "field": "valid_to",
            "expected": "not_expired",
            "actual": valid_to,
            "difference": difference,
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


def _normalize_comparison_value(field: str, value: str | None) -> str:
    text = unicodedata.normalize("NFKC", _normalize_text(value))
    if field == "subject_name":
        text = re.sub(r"[（(]个体工商户[）)]$", "", text)
        text = re.sub(r"个体工商户$", "", text)
    if field == "business_address":
        for formal_name, short_name in _AUTONOMOUS_REGION_SHORT_NAMES.items():
            if text.startswith(formal_name):
                text = short_name + text[len(formal_name):]
                break
    return text


def _normalize_date_value(value: str | None) -> str:
    text = _normalize_text(value)
    match = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日?", text)
    if match:
        year, month, day = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return text


_AUTONOMOUS_REGION_SHORT_NAMES = {
    "内蒙古自治区": "内蒙古",
    "广西壮族自治区": "广西",
    "西藏自治区": "西藏",
    "宁夏回族自治区": "宁夏",
    "新疆维吾尔自治区": "新疆",
}


def _difference(expected: str | None, actual: str | None) -> str:
    if not expected:
        return "expected_missing"
    if not actual:
        return "actual_missing"
    return "value_mismatch"
