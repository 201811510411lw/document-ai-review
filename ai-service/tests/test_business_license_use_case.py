from app.models import ReviewDocumentInput, ReviewInput, ReviewStatus, RiskLevel
from app.services.review_service import ReviewService


def test_business_license_review_rejects_text_only_input():
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
    assert result.status == ReviewStatus.PENDING_MANUAL_REVIEW
    assert result.risk_level == RiskLevel.HIGH
    assert result.needs_manual_review is True
    assert result.manual_review.reasons[0] == "营业执照审核不支持文本输入，请提供 PDF/JPG/JPEG/PNG 文件"
    assert result.skill_result["document_input"]["input_type"] == "unsupported_text"
    assert result.skill_result["source_evidence"]["source"]["record_id"] == "cert-business-001"


def test_business_license_review_rejects_stub_text_input():
    result = ReviewService().review(
        ReviewInput(
            file=ReviewDocumentInput(stub_text="营业执照\n名称：成都示例商贸有限公司"),
            supplier_name="成都示例商贸有限公司",
            supplier_credit_code="91510100MA0000000X",
            declared_document_type="business_license",
        ),
        use_case_name="business_license",
    )

    assert result.status == ReviewStatus.PENDING_MANUAL_REVIEW
    assert result.risk_level == RiskLevel.HIGH
    assert result.needs_manual_review is True
    assert result.manual_review.reasons[0] == "营业执照审核不支持文本输入，请提供 PDF/JPG/JPEG/PNG 文件"


def test_business_license_review_can_be_selected_by_declared_document_type():
    result = ReviewService().review(
        ReviewInput(
            file=ReviewDocumentInput(stub_text="营业执照"),
            supplier_name="成都示例商贸有限公司",
            supplier_credit_code="91510100MA0000000X",
            declared_document_type="business_license",
        )
    )

    assert result.use_case_name == "business_license"
