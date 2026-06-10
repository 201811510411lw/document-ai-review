from datetime import date

from app.models import ReviewInput, ReviewInputContext, RiskLevel
from app.rules import RuleContext, RuleStatus
from app.capabilities.food_license.schemas import FoodLicenseNormalizedFields
from app.capabilities.food_license.rules import (
    FoodLicenseCreditCodeMatchRule,
    FoodLicenseDocumentTypeRule,
    FoodLicenseSubjectNameMatchRule,
    FoodLicenseValidityRule,
    build_food_license_rules,
)


def build_context(
    *,
    document_type: str | None = "food_license",
    supplier_name: str = "成都示例食品有限公司",
    supplier_credit_code: str = "91510100MA00000000",
    normalized_fields: FoodLicenseNormalizedFields | None = None,
    current_date: date = date(2026, 6, 9),
) -> RuleContext:
    return RuleContext(
        input_context=ReviewInputContext(
            task_id="review-task-rules",
            input=ReviewInput(
                ocr_text="食品经营许可证",
                supplier_name=supplier_name,
                supplier_credit_code=supplier_credit_code,
                declared_document_type="food_license",
            ),
            skill_name="food_license",
            skill_version="v1",
            ruleset_version="food-license-rules-v1",
        ),
        facts={
            "document_type": document_type,
            "normalized_fields": normalized_fields
            or FoodLicenseNormalizedFields(
                subject_name="成都示例食品有限公司",
                credit_code="91510100MA00000000",
                license_no="JY15101000000000",
                business_items=["预包装食品销售"],
                valid_to="2028-06-05",
            ),
            "current_date": current_date,
        },
    )


def test_build_food_license_rules_keeps_stub_and_loads_basic_rules():
    rules = build_food_license_rules()

    assert [rule.code for rule in rules] == [
        "FOOD_LICENSE_RULE_ENGINE_STUB",
        "FOOD_LICENSE_TYPE_MATCH",
        "FOOD_LICENSE_SUBJECT_NAME_MATCH",
        "FOOD_LICENSE_CREDIT_CODE_MATCH",
        "FOOD_LICENSE_VALIDITY_PERIOD",
    ]


def test_document_type_rule_passes_for_food_license():
    result = FoodLicenseDocumentTypeRule().evaluate(build_context())

    assert result.status == RuleStatus.PASSED
    assert result.details["actual"] == "food_license"


def test_document_type_rule_fails_for_unknown_document_type():
    result = FoodLicenseDocumentTypeRule().evaluate(
        build_context(document_type="unknown"),
    )

    assert result.status == RuleStatus.FAILED
    assert result.risk_level_on_failure == RiskLevel.HIGH
    assert result.details["expected"] == "food_license"
    assert result.details["actual"] == "unknown"


def test_document_type_rule_requires_manual_review_when_missing():
    result = FoodLicenseDocumentTypeRule().evaluate(
        build_context(document_type=None),
    )

    assert result.status == RuleStatus.ERROR
    assert result.details["field"] == "document_type"
    assert result.details["reason"] == "missing_or_unreadable_field"


def test_subject_name_rule_matches_after_whitespace_normalization():
    result = FoodLicenseSubjectNameMatchRule().evaluate(
        build_context(
            supplier_name="成都示例食品有限公司",
            normalized_fields=FoodLicenseNormalizedFields(
                subject_name="成都 示例 食品 有限公司",
            ),
        ),
    )

    assert result.status == RuleStatus.PASSED


def test_subject_name_rule_fails_on_mismatch():
    result = FoodLicenseSubjectNameMatchRule().evaluate(
        build_context(
            supplier_name="成都示例食品有限公司",
            normalized_fields=FoodLicenseNormalizedFields(
                subject_name="成都另一家食品有限公司",
            ),
        ),
    )

    assert result.status == RuleStatus.FAILED
    assert result.risk_level_on_failure == RiskLevel.MEDIUM
    assert result.details["field"] == "subject_name"


def test_subject_name_rule_requires_manual_review_when_missing():
    result = FoodLicenseSubjectNameMatchRule().evaluate(
        build_context(normalized_fields=FoodLicenseNormalizedFields()),
    )

    assert result.status == RuleStatus.ERROR
    assert result.details["field"] == "subject_name"


def test_credit_code_rule_matches_after_case_and_whitespace_normalization():
    result = FoodLicenseCreditCodeMatchRule().evaluate(
        build_context(
            supplier_credit_code="91510100MA0000000X",
            normalized_fields=FoodLicenseNormalizedFields(
                credit_code="91510100ma0000000x",
            ),
        ),
    )

    assert result.status == RuleStatus.PASSED


def test_credit_code_rule_fails_on_mismatch():
    result = FoodLicenseCreditCodeMatchRule().evaluate(
        build_context(
            supplier_credit_code="91510100MA00000000",
            normalized_fields=FoodLicenseNormalizedFields(
                credit_code="91510100MA99999999",
            ),
        ),
    )

    assert result.status == RuleStatus.FAILED
    assert result.risk_level_on_failure == RiskLevel.HIGH
    assert result.details["field"] == "credit_code"


def test_credit_code_rule_requires_manual_review_when_missing():
    result = FoodLicenseCreditCodeMatchRule().evaluate(
        build_context(normalized_fields=FoodLicenseNormalizedFields()),
    )

    assert result.status == RuleStatus.ERROR
    assert result.details["field"] == "credit_code"


def test_validity_rule_passes_when_not_expired_or_expiring():
    result = FoodLicenseValidityRule().evaluate(
        build_context(
            current_date=date(2026, 6, 9),
            normalized_fields=FoodLicenseNormalizedFields(valid_to="2028-06-05"),
        ),
    )

    assert result.status == RuleStatus.PASSED
    assert result.details["days_until_expiry"] > 30


def test_validity_rule_fails_high_risk_when_expired():
    result = FoodLicenseValidityRule().evaluate(
        build_context(
            current_date=date(2026, 6, 9),
            normalized_fields=FoodLicenseNormalizedFields(valid_to="2026-06-08"),
        ),
    )

    assert result.status == RuleStatus.FAILED
    assert result.risk_level_on_failure == RiskLevel.HIGH
    assert result.details["days_until_expiry"] == -1


def test_validity_rule_fails_medium_risk_when_expiring_within_thirty_days():
    result = FoodLicenseValidityRule().evaluate(
        build_context(
            current_date=date(2026, 6, 9),
            normalized_fields=FoodLicenseNormalizedFields(valid_to="2026-07-09"),
        ),
    )

    assert result.status == RuleStatus.FAILED
    assert result.risk_level_on_failure == RiskLevel.MEDIUM
    assert result.details["days_until_expiry"] == 30


def test_validity_rule_requires_manual_review_when_missing_or_unreadable():
    missing = FoodLicenseValidityRule().evaluate(
        build_context(normalized_fields=FoodLicenseNormalizedFields()),
    )
    unreadable = FoodLicenseValidityRule().evaluate(
        build_context(
            normalized_fields=FoodLicenseNormalizedFields(valid_to="无法识别"),
        ),
    )

    assert missing.status == RuleStatus.ERROR
    assert missing.details["field"] == "valid_to"
    assert unreadable.status == RuleStatus.ERROR
    assert unreadable.details["field"] == "valid_to"
