from app.models import ManualReviewStatus, ReviewInput, ReviewStatus, RiskLevel
from app.services.review_service import ReviewService


def test_qc_document_review_reviews_product_report_from_ocr_text():
    result = ReviewService().review(
        ReviewInput(
            ocr_text="""
            产品检验报告
            样品名称：麻辣牛肉
            受检单位：成都示例食品有限公司
            批号：20260601-A
            签发日期：2026年06月10日
            检验结论：经检验，所检项目符合要求。
            """,
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="product_report",
        ),
        use_case_name="qc_document_review",
    )

    assert result.use_case_name == "qc_document_review"
    assert result.document_type == "product_report"
    assert result.status == ReviewStatus.REVIEWED
    assert result.risk_level == RiskLevel.NONE
    assert result.needs_manual_review is False
    assert result.manual_review.status == ManualReviewStatus.NOT_REQUIRED
    assert result.skill_result["document_classification"]["document_type"] == "product_report"
    assert result.skill_result["extracted_fields"]["product_name"] == "麻辣牛肉"


def test_qc_document_review_marks_missing_text_for_manual_review():
    result = ReviewService().review(
        ReviewInput(
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="product_report",
        ),
        use_case_name="qc_document_review",
    )

    assert result.document_type == "product_report"
    assert result.status == ReviewStatus.PENDING_MANUAL_REVIEW
    assert result.risk_level == RiskLevel.MEDIUM
    assert result.needs_manual_review is True
    assert result.manual_review.status == ManualReviewStatus.PENDING
    assert "文本为空" in result.manual_review.reasons[0]


def test_qc_document_review_fails_negative_product_report_conclusion():
    result = ReviewService().review(
        ReviewInput(
            ocr_text="""
            产品检验报告
            样品名称：麻辣牛肉
            受检单位：成都示例食品有限公司
            批号：20260601-A
            签发日期：2026年06月10日
            检验结论：不合格
            """,
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="product_report",
        ),
        use_case_name="qc_document_review",
    )

    assert result.status == ReviewStatus.FAILED
    assert result.risk_level == RiskLevel.HIGH
    assert result.needs_manual_review is False
