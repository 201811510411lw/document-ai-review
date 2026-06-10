from app.models import ManualReviewStatus, ReviewInput, ReviewStatus, RiskLevel
from app.services.review_service import ReviewService


def test_business_license_review_returns_review_result_for_text_input():
    result = ReviewService().review(
        ReviewInput(
            ocr_text="""
            营业执照
            统一社会信用代码：91510100MA0000000X
            名称：成都示例商贸有限公司
            住所：成都市高新区天府大道 1 号
            法定代表人：张三
            营业期限：2020年01月02日至2030年01月01日
            """,
            supplier_name="成都示例商贸有限公司",
            supplier_credit_code="91510100MA0000000X",
            declared_document_type="business_license",
            source={"record_id": "cert-business-001"},
        ),
        use_case_name="business_license",
    )

    assert result.use_case_name == "business_license"
    assert result.document_type == "business_license"
    assert result.capability_names == ["business_license"]
    assert result.status == ReviewStatus.REVIEWED
    assert result.risk_level == RiskLevel.NONE
    assert result.needs_manual_review is False
    assert result.manual_review.status == ManualReviewStatus.NOT_REQUIRED
    assert result.skill_result["document_classification"]["document_type"] == "business_license"
    assert result.skill_result["extracted_fields"]["subject_name"] == "成都示例商贸有限公司"
    assert result.skill_result["source_evidence"]["source"]["record_id"] == "cert-business-001"


def test_business_license_review_routes_non_business_license_text_to_manual_review():
    result = ReviewService().review(
        ReviewInput(
            ocr_text="产品检验报告\n检验结论：合格",
            supplier_name="成都示例商贸有限公司",
            supplier_credit_code="91510100MA0000000X",
            declared_document_type="business_license",
        ),
        use_case_name="business_license",
    )

    assert result.status == ReviewStatus.PENDING_MANUAL_REVIEW
    assert result.risk_level == RiskLevel.HIGH
    assert result.needs_manual_review is True
    assert "文档类型不匹配" in result.manual_review.reasons


def test_business_license_review_can_be_selected_by_declared_document_type():
    result = ReviewService().review(
        ReviewInput(
            ocr_text="""
            营业执照
            统一社会信用代码：91510100MA0000000X
            名称：成都示例商贸有限公司
            营业期限：2020年01月02日至2030年01月01日
            """,
            supplier_name="成都示例商贸有限公司",
            supplier_credit_code="91510100MA0000000X",
            declared_document_type="business_license",
        )
    )

    assert result.use_case_name == "business_license"
