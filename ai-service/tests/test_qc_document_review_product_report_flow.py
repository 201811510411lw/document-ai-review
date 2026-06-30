from app.models import ManualReviewStatus, ReviewInput, ReviewStatus, RiskLevel
from app.services.review_service import ReviewService
from app.tools.remote_document import RemoteDocument
from app.workflows.qc_document import workflow as qc_document_workflow
from tests.pdf_helpers import write_blank_pdf, write_minimal_pdf


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


def test_qc_document_review_routes_unclear_product_report_to_manual_review():
    result = ReviewService().review(
        ReviewInput(
            ocr_text="""
            产品检验报告
            样品名称：麻辣牛肉
            受检单位：成都示例食品有限公司
            批号：20260601-A
            签发日期：2026年06月10日
            检验结论：详见报告正文
            """,
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="product_report",
        ),
        use_case_name="qc_document_review",
    )

    assert result.status == ReviewStatus.PENDING_MANUAL_REVIEW
    assert result.risk_level == RiskLevel.MEDIUM
    assert result.needs_manual_review is True
    assert result.manual_review.status == ManualReviewStatus.PENDING
    assert "检验结论不明确" in result.manual_review.reasons


def test_qc_document_review_fails_expired_product_report_validity():
    result = ReviewService().review(
        ReviewInput(
            ocr_text="""
            产品检验报告
            报告编号：BG-20250101-001
            样品名称：麻辣牛肉
            委托单位：成都示例食品有限公司
            批号：20250101-A
            签发日期：2025年01月01日
            检验结论：合格
            """,
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="product_report",
        ),
        use_case_name="qc_document_review",
    )

    assert result.status == ReviewStatus.FAILED
    assert result.risk_level == RiskLevel.HIGH
    validity_rule = _rule_by_code(result, "PRODUCT_REPORT_VALIDITY_PERIOD")
    assert validity_rule.passed is False
    assert validity_rule.details["valid_to"] == "2025-06-30"


def test_qc_document_review_routes_nearly_expired_product_report_to_manual_review():
    result = ReviewService().review(
        ReviewInput(
            ocr_text="""
            产品检验报告
            报告编号：BG-20260110-001
            样品名称：麻辣牛肉
            委托单位：成都示例食品有限公司
            批号：20260110-A
            签发日期：2026年01月10日
            检验结论：合格
            """,
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="product_report",
        ),
        use_case_name="qc_document_review",
    )

    assert result.status == ReviewStatus.PENDING_MANUAL_REVIEW
    assert result.risk_level == RiskLevel.MEDIUM
    validity_rule = _rule_by_code(result, "PRODUCT_REPORT_VALIDITY_PERIOD")
    assert validity_rule.passed is False
    assert validity_rule.details["valid_to"] == "2026-07-09"
    assert 0 <= validity_rule.details["days_until_expiry"] <= 30


def test_qc_document_review_extracts_product_report_from_remote_pdf_text_layer(
    tmp_path,
    monkeypatch,
):
    pdf_path = tmp_path / "product-report.pdf"
    write_minimal_pdf(
        pdf_path,
        """
        产品检验报告
        报告编号：A2260511467101001C
        样品名称：鲜切蛋糕(蓝莓风味)
        委托单位：广东乃一口食品有限公司
        批号：TS10970001
        生产日期：2026年06月20日
        签发日期：2026年06月29日
        检验结论：所检项目符合相关食品安全标准要求
        """,
    )

    class StubDownloader:
        def download(self, file_url):
            return RemoteDocument(
                source_url=file_url,
                content=pdf_path.read_bytes(),
                file_type="pdf",
                mime_type="application/pdf",
                status_code=200,
                headers={"content-type": "application/pdf"},
            )

    monkeypatch.setattr(qc_document_workflow, "qc_document_remote_downloader", StubDownloader())

    result = ReviewService().review(
        ReviewInput(
            file={
                "file_uri": "https://files.example.test/product-report.pdf",
                "file_name": "product-report.pdf",
            },
            supplier_name="广东乃一口食品有限公司",
            supplier_credit_code="",
            declared_document_type="product_report",
        ),
        use_case_name="qc_document_review",
    )

    assert result.document_type == "product_report"
    assert result.status == ReviewStatus.REVIEWED
    assert result.skill_result["document_input"]["input_type"] == "remote_pdf_text"
    assert result.skill_result["document_input"]["source_url"] == (
        "https://files.example.test/product-report.pdf"
    )
    assert result.skill_result["extracted_fields"]["product_name"] == "鲜切蛋糕(蓝莓风味)"
    assert result.skill_result["extraction_metadata"]["pdf_text_extractor"]["status"] == (
        "extracted"
    )


def test_qc_document_review_routes_blank_remote_pdf_to_manual_review(tmp_path, monkeypatch):
    pdf_path = tmp_path / "blank-product-report.pdf"
    write_blank_pdf(pdf_path)

    class StubDownloader:
        def download(self, file_url):
            return RemoteDocument(
                source_url=file_url,
                content=pdf_path.read_bytes(),
                file_type="pdf",
                mime_type="application/pdf",
                status_code=200,
                headers={"content-type": "application/pdf"},
            )

    monkeypatch.setattr(qc_document_workflow, "qc_document_remote_downloader", StubDownloader())

    result = ReviewService().review(
        ReviewInput(
            file={
                "file_uri": "https://files.example.test/blank-product-report.pdf",
                "file_name": "blank-product-report.pdf",
            },
            supplier_name="广东乃一口食品有限公司",
            supplier_credit_code="",
            declared_document_type="product_report",
        ),
        use_case_name="qc_document_review",
    )

    assert result.status == ReviewStatus.PENDING_MANUAL_REVIEW
    assert result.needs_manual_review is True
    assert result.skill_result["document_input"]["input_type"] == "remote_pdf_empty_text"
    assert result.skill_result["extraction_metadata"]["pdf_text_extractor"]["status"] == (
        "empty_text_layer"
    )


def _rule_by_code(result, rule_code):
    for rule in result.rule_results:
        if rule.rule_code == rule_code:
            return rule
    raise AssertionError(f"rule not found: {rule_code}")
