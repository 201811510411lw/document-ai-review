from datetime import date

from app.capabilities.business_license.rules import evaluate_business_license_rules
from app.models import RiskLevel


BASE_FIELDS = {
    "document_type": "business_license",
    "subject_name": "成都示例商贸有限公司",
    "credit_code": "91510100MA0000000X",
    "business_address": "成都市高新区天府大道 1 号",
    "legal_person": "张三",
    "valid_to": "2030-01-01",
}


def test_business_license_rules_pass_when_core_fields_match():
    result = evaluate_business_license_rules(
        document_type="business_license",
        source_subject_name="成都示例商贸有限公司",
        source_credit_code="91510100MA0000000X",
        extracted_fields=BASE_FIELDS,
        current_date=date(2026, 6, 10),
    )

    assert result["risk_level"] == RiskLevel.NONE
    assert result["needs_manual_review"] is False
    assert [item.rule_code for item in result["rule_results"]] == [
        "BUSINESS_LICENSE_TYPE_MATCH",
        "BUSINESS_LICENSE_SUBJECT_NAME_MATCH",
        "BUSINESS_LICENSE_CREDIT_CODE_MATCH",
        "BUSINESS_LICENSE_VALIDITY_PERIOD",
        "BUSINESS_LICENSE_REQUIRED_FIELDS_PRESENT",
    ]
    assert all(item.passed is True for item in result["rule_results"])


def test_business_license_rules_flag_subject_name_mismatch():
    result = evaluate_business_license_rules(
        document_type="business_license",
        source_subject_name="成都示例商贸有限公司",
        source_credit_code="91510100MA0000000X",
        extracted_fields={**BASE_FIELDS, "subject_name": "成都另一家公司"},
        current_date=date(2026, 6, 10),
    )

    assert result["risk_level"] == RiskLevel.MEDIUM
    assert result["needs_manual_review"] is True
    assert "主体名称与来源信息不一致" in result["manual_review_reasons"]
    assert _rule(result, "BUSINESS_LICENSE_SUBJECT_NAME_MATCH").passed is False


def test_business_license_rules_flag_missing_credit_code_as_high_risk():
    result = evaluate_business_license_rules(
        document_type="business_license",
        source_subject_name="成都示例商贸有限公司",
        source_credit_code="91510100MA0000000X",
        extracted_fields={**BASE_FIELDS, "credit_code": None},
        current_date=date(2026, 6, 10),
    )

    assert result["risk_level"] == RiskLevel.HIGH
    assert "统一社会信用代码缺失" in result["manual_review_reasons"]
    assert _rule(result, "BUSINESS_LICENSE_CREDIT_CODE_MATCH").passed is False
    assert _rule(result, "BUSINESS_LICENSE_REQUIRED_FIELDS_PRESENT").passed is False


def test_business_license_rules_flag_expired_license_as_high_risk():
    result = evaluate_business_license_rules(
        document_type="business_license",
        source_subject_name="成都示例商贸有限公司",
        source_credit_code="91510100MA0000000X",
        extracted_fields={**BASE_FIELDS, "valid_to": "2026-01-01"},
        current_date=date(2026, 6, 10),
    )

    assert result["risk_level"] == RiskLevel.HIGH
    assert "营业执照已过期" in result["manual_review_reasons"]
    assert _rule(result, "BUSINESS_LICENSE_VALIDITY_PERIOD").passed is False


def test_business_license_rules_route_unparseable_validity_to_manual_review():
    result = evaluate_business_license_rules(
        document_type="business_license",
        source_subject_name="成都示例商贸有限公司",
        source_credit_code="91510100MA0000000X",
        extracted_fields={**BASE_FIELDS, "valid_to": None},
        current_date=date(2026, 6, 10),
    )

    assert result["risk_level"] == RiskLevel.MEDIUM
    assert result["needs_manual_review"] is True
    assert "有效期无法判断" in result["manual_review_reasons"]


def _rule(result: dict, rule_code: str):
    return next(item for item in result["rule_results"] if item.rule_code == rule_code)
