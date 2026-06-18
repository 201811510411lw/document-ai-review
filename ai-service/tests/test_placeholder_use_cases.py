from app.models import (
    ManualReviewStatus,
    ReviewInput,
    ReviewStatus,
)
from app.services.review_service import ReviewService


def test_contract_review_runtime_entry_returns_clear_not_implemented_result():
    result = ReviewService().review(
        ReviewInput(
            ocr_text="占位输入",
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="contract_review",
        ),
        use_case_name="contract_review",
    )
    payload = result.model_dump(mode="json")

    assert result.status == ReviewStatus.PENDING_MANUAL_REVIEW
    assert result.needs_manual_review is True
    assert result.manual_review.status == ManualReviewStatus.PENDING
    assert payload["skill_result"]["implementation_status"] == "not_implemented"
    assert "尚未执行业务审核" in result.summary


def test_tobacco_license_consistency_without_inputs_routes_manual_review():
    result = ReviewService().review(
        ReviewInput(
            ocr_text="占位输入",
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="tobacco_license_consistency_review",
        ),
        use_case_name="tobacco_license_consistency_review",
    )

    payload = result.model_dump(mode="json")

    assert payload["skill_result"]["implementation_status"] == "implemented"
    assert result.document_type == "business_tobacco_consistency"
    assert result.status == ReviewStatus.PENDING_MANUAL_REVIEW
