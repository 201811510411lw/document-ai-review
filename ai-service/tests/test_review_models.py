from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models import (
    AuditEvent,
    ManualReview,
    ManualReviewStatus,
    ReviewInput,
    ReviewInputContext,
    ReviewResult,
    ReviewStatus,
    RiskLevel,
    RuleResult,
)
from app.capabilities.food_license.schemas import (
    FoodLicenseCapabilityResult,
    FoodLicenseDocumentClassification,
    FoodLicenseExtractedFields,
    FoodLicenseNormalizedFields,
)


def test_review_result_serializes_platform_fields_and_skill_result_boundary():
    now = datetime(2026, 6, 8, 14, 30, tzinfo=timezone.utc)
    skill_result = FoodLicenseCapabilityResult(
        document_classification=FoodLicenseDocumentClassification(
            document_type="food_license",
            confidence=0.98,
            reasons=["OCR 文本包含食品经营许可证编号"],
        ),
        extracted_fields=FoodLicenseExtractedFields(
            subject_name="成都示例食品有限公司",
            credit_code="91510100MA00000000",
            license_no="JY15101000000000",
            business_items=["预包装食品销售", "散装食品销售"],
            valid_to="2028-01-01",
        ),
        normalized_fields=FoodLicenseNormalizedFields(
            subject_name="成都示例食品有限公司",
            credit_code="91510100MA00000000",
            license_no="JY15101000000000",
            business_items=["预包装食品销售", "散装食品销售"],
            valid_to="2028-01-01",
        ),
    )

    result = ReviewResult(
        task_id="review-task-001",
        use_case_name="food_license",
        use_case_version="v1",
        skill_name="food_license",
        skill_version="v1",
        ruleset_version="food-license-rules-v1",
        capability_names=["food_license"],
        document_type="food_license",
        status=ReviewStatus.REVIEWED,
        risk_level=RiskLevel.NONE,
        needs_manual_review=False,
        rule_results=[
            RuleResult(
                rule_code="FOOD_LICENSE_EXISTS",
                rule_name="证照是否存在",
                passed=True,
                risk_level_on_failure=RiskLevel.HIGH,
                message="已检测到可审核的 OCR 文本",
            )
        ],
        summary="未发现明显风险，可自动通过。",
        manual_review=ManualReview(status=ManualReviewStatus.NOT_REQUIRED),
        audit_events=[
            AuditEvent(
                event_type="review.completed",
                message="审核完成",
                occurred_at=now,
            )
        ],
        created_at=now,
        updated_at=now,
        skill_result=skill_result,
    )

    payload = result.model_dump(mode="json")

    assert list(payload.keys()) == [
        "task_id",
        "use_case_name",
        "use_case_version",
        "skill_name",
        "skill_version",
        "ruleset_version",
        "capability_names",
        "document_type",
        "status",
        "risk_level",
        "needs_manual_review",
        "rule_results",
        "summary",
        "manual_review",
        "audit_events",
        "created_at",
        "updated_at",
        "skill_result",
    ]
    assert payload["status"] == "REVIEWED"
    assert payload["risk_level"] == "NONE"
    assert payload["rule_results"][0]["risk_level_on_failure"] == "HIGH"
    assert "extracted_fields" not in payload
    assert "normalized_fields" not in payload
    assert "document_classification" not in payload
    assert payload["skill_result"]["extracted_fields"]["license_no"] == "JY15101000000000"
    assert payload["skill_result"]["normalized_fields"]["business_items"] == [
        "预包装食品销售",
        "散装食品销售",
    ]
    assert payload["skill_result"]["document_classification"]["document_type"] == "food_license"


def test_review_input_context_keeps_document_input_separate_from_skill_result():
    review_input = ReviewInput(
        ocr_text="食品经营许可证\n许可证编号：JY15101000000000",
        supplier_name="成都示例食品有限公司",
        supplier_credit_code="91510100MA00000000",
        supplier_address="成都市示例区示例路 100 号",
        declared_document_type="food_license",
        source={"input_type": "ocr_text"},
        options={"sync": True},
    )

    context = ReviewInputContext(
        task_id="review-task-001",
        input=review_input,
        use_case_name="food_license",
        use_case_version="v1",
        ruleset_version="food-license-rules-v1",
    )

    payload = context.model_dump(mode="json")

    assert payload["input"]["ocr_text"].startswith("食品经营许可证")
    assert payload["input"]["supplier_credit_code"] == "91510100MA00000000"
    assert payload["use_case_name"] == "food_license"
    assert "skill_result" not in payload


def test_review_result_rejects_food_license_fields_at_top_level():
    now = datetime(2026, 6, 8, 14, 30, tzinfo=timezone.utc)
    base_payload = {
        "task_id": "review-task-001",
        "use_case_name": "food_license",
        "use_case_version": "v1",
        "skill_name": "food_license",
        "skill_version": "v1",
        "ruleset_version": "food-license-rules-v1",
        "capability_names": ["food_license"],
        "document_type": "food_license",
        "status": "REVIEWED",
        "risk_level": "NONE",
        "needs_manual_review": False,
        "rule_results": [],
        "summary": "未发现明显风险。",
        "manual_review": {"status": "NOT_REQUIRED"},
        "audit_events": [],
        "created_at": now,
        "updated_at": now,
        "skill_result": {"extracted_fields": {"license_no": "JY15101000000000"}},
        "extracted_fields": {"license_no": "JY15101000000000"},
    }

    with pytest.raises(ValidationError) as exc_info:
        ReviewResult.model_validate(base_payload)

    assert exc_info.value.errors()[0]["loc"] == ("extracted_fields",)
