from app.models import ReviewInput, ReviewStatus, RiskLevel
from app.services.review_service import ReviewService


BASE_BUSINESS_FIELDS = {
    "document_type": "business_license",
    "subject_name": "成都示例烟草商行",
    "business_address": "成都市高新区天府大道 1 号",
    "legal_person": "张三",
}

BASE_TOBACCO_FIELDS = {
    "document_type": "tobacco_license",
    "subject_name": "成都示例烟草商行",
    "business_address": "成都市高新区天府大道 1 号",
    "legal_person": "张三",
    "valid_to": "2099-12-31",
}


def test_tobacco_license_consistency_all_match_passes():
    result = _review()

    assert result.document_type == "business_tobacco_consistency"
    assert result.status == ReviewStatus.REVIEWED
    assert result.risk_level == RiskLevel.NONE
    assert result.needs_manual_review is False
    assert result.skill_result["comparison"]["differences"] == []


def test_tobacco_license_consistency_name_mismatch_routes_manual_review():
    result = _review(tobacco_fields={**BASE_TOBACCO_FIELDS, "subject_name": "成都其他烟草商行"})

    assert result.status == ReviewStatus.PENDING_MANUAL_REVIEW
    assert result.risk_level == RiskLevel.MEDIUM
    assert _failed_codes(result) == ["BUSINESS_TOBACCO_SUBJECT_NAME_MATCH"]


def test_tobacco_license_consistency_address_mismatch_routes_manual_review():
    result = _review(tobacco_fields={**BASE_TOBACCO_FIELDS, "business_address": "成都市锦江区 2 号"})

    assert result.status == ReviewStatus.PENDING_MANUAL_REVIEW
    assert "BUSINESS_TOBACCO_ADDRESS_MATCH" in _failed_codes(result)


def test_tobacco_license_consistency_person_mismatch_routes_manual_review():
    result = _review(tobacco_fields={**BASE_TOBACCO_FIELDS, "legal_person": "李四"})

    assert result.status == ReviewStatus.PENDING_MANUAL_REVIEW
    assert "BUSINESS_TOBACCO_PERSON_MATCH" in _failed_codes(result)


def test_tobacco_license_consistency_expired_tobacco_license_is_high_risk():
    result = _review(tobacco_fields={**BASE_TOBACCO_FIELDS, "valid_to": "2000-01-01"})

    assert result.status == ReviewStatus.PENDING_MANUAL_REVIEW
    assert result.risk_level == RiskLevel.HIGH
    assert "BUSINESS_TOBACCO_TOBACCO_VALIDITY" in _failed_codes(result)


def test_tobacco_license_consistency_type_errors_are_high_risk():
    result = _review(
        business_fields={**BASE_BUSINESS_FIELDS, "document_type": "food_license"},
        tobacco_fields={**BASE_TOBACCO_FIELDS, "document_type": "business_license"},
    )

    assert result.status == ReviewStatus.PENDING_MANUAL_REVIEW
    assert result.risk_level == RiskLevel.HIGH
    assert "BUSINESS_LICENSE_TYPE_FOR_CONSISTENCY" in _failed_codes(result)
    assert "TOBACCO_LICENSE_TYPE_FOR_CONSISTENCY" in _failed_codes(result)


def _review(
    *,
    business_fields: dict | None = None,
    tobacco_fields: dict | None = None,
):
    return ReviewService().review(
        ReviewInput(
            ocr_text="structured consistency input",
            supplier_name="成都示例烟草商行",
            supplier_credit_code="91510100MA0000000X",
            declared_document_type="business_tobacco_consistency",
            options={
                "business_license_fields": business_fields or BASE_BUSINESS_FIELDS,
                "tobacco_license_fields": tobacco_fields or BASE_TOBACCO_FIELDS,
            },
        ),
        use_case_name="tobacco_license_consistency_review",
    )


def _failed_codes(result):
    return [rule.rule_code for rule in result.rule_results if not rule.passed]
