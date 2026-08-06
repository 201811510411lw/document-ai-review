from io import BytesIO

import pytest
from PIL import Image

from app.models import ReviewInput
from app.services.review_service import ReviewService
from app.tools.remote_document import RemoteDocument
from app.workflows.qc_document import workflow as qc_document_workflow
from app.workflows.qc_document import batch_report_extraction
from app.workflows.qc_document.batch_report_extraction import extract_batch_report_fields


def test_qc_document_review_reviews_batch_report_from_ocr_text():
    result = ReviewService().review(
        ReviewInput(
            supplier_name="广州市秀雅秀贸易有限公司（常温）",
            supplier_credit_code="",
            declared_document_type="batch_report",
            ocr_text="""
            商品批次报告
            厂名：广州市秀雅秀贸易有限公司（常温）
            产品名称：游世佳族金唱片面包
            生产日期：2026年05月08日
            """,
            source={
                "sku_name": "游世佳族金唱片面包",
                "production_date": "2026-05-08",
            },
        ),
        use_case_name="qc_document_review",
    )

    assert result.document_type == "batch_report"
    assert result.status == "REVIEWED"
    assert result.needs_manual_review is False
    assert result.skill_result["extracted_fields"]["product_name"] == "游世佳族金唱片面包"
    assert result.skill_result["extracted_fields"]["production_date"] == "2026-05-08"


def test_qc_document_review_routes_blank_batch_report_to_manual_review():
    result = ReviewService().review(
        ReviewInput(
            supplier_name="广州市秀雅秀贸易有限公司（常温）",
            supplier_credit_code="",
            declared_document_type="batch_report",
            source={
                "sku_name": "游世佳族金唱片面包",
                "production_date": "2026-05-08",
            },
        ),
        use_case_name="qc_document_review",
    )

    assert result.document_type == "batch_report"
    assert result.status == "PENDING_MANUAL_REVIEW"
    assert result.needs_manual_review is True
    assert "批次报告附件未获取到可审核文本" in result.manual_review.reasons[0]


def test_qc_document_review_extracts_multiline_sample_name_and_title_producer():
    result = ReviewService().review(
        ReviewInput(
            supplier_name="内蒙古伊利实业集团股份有限公司",
            supplier_credit_code="",
            declared_document_type="batch_report",
            ocr_text="""
            液态奶事业部
            湖北黄冈伊利乳业有限责任公司产品检验报告
            编号：2025050719829-YLHG-2025050033
            样品名称
            伊刻活泉现泡茶茉莉花茶固体
            饮料
            生产日期 20250506
            检验结论 检测结果符合标准要求，产品合格。
            """,
            source={
                "vendor_name": "内蒙古伊利实业集团股份有限公司",
                "sku_name": "伊利伊刻活泉现泡茶茉莉花茶",
                "production_date": "2026-04-07",
            },
        ),
        use_case_name="qc_document_review",
    )

    fields = result.skill_result["extracted_fields"]
    assert fields["producer_name"] == "湖北黄冈伊利乳业有限责任公司"
    assert fields["product_name"] == "伊刻活泉现泡茶茉莉花茶固体"
    assert fields["production_date"] == "2025-05-06"
    assert result.status == "PENDING_MANUAL_REVIEW"
    assert "生产日期" in result.manual_review.reasons[-1]


def test_batch_report_does_not_treat_following_headers_as_values():
    extracted, metadata = extract_batch_report_fields(
        """
        商品批次报告
        产品名称
        生产日期
        生产批号
        Batch No.
        """
    )

    assert extracted.product_name is None
    assert extracted.production_date is None
    assert extracted.batch_no is None
    assert "product_name" in metadata["missing_required_fields"]


def test_batch_report_prefers_direct_production_date_over_later_expiry_batch_field(
    monkeypatch,
):
    monkeypatch.setattr(
        batch_report_extraction,
        "_extract_with_llm",
        lambda _text: {
            "product_name": "超能白桃苏打洗洁精",
            "producer_name": "纳爱斯集团有限公司",
            "company_name": "纳爱斯集团有限公司",
            "production_date": "2028-09-21",
            "batch_no": None,
        },
    )

    extracted, metadata = extract_batch_report_fields(
        """
        产品名称 超能白桃苏打洗洁精
        生产日期
        或 批号
        20250921
        生产日期和保质期或生产批号和限期使用日期 20280921A1353
        """
    )

    assert extracted.production_date == "2025-09-21"
    assert extracted.batch_no == "A1353"
    assert metadata["field_reconciliation"]["production_date"] == {
        "llm": "2028-09-21",
        "text_evidence": "2025-09-21",
        "selected": "text_evidence",
    }


def test_batch_report_extracts_direct_production_date_from_flattened_table_text(
    monkeypatch,
):
    monkeypatch.setattr(
        batch_report_extraction,
        "_extract_with_llm",
        lambda _text: {
            "production_date": "2028-09-21",
            "batch_no": None,
            "product_name": "超能白桃苏打洗洁精",
            "producer_name": "纳爱斯集团有限公司",
        },
    )

    extracted, _metadata = extract_batch_report_fields(
        "产品名称 超能白桃苏打洗洁精 生产日期 20250921 "
        "生产日期和保质期或生产批号和限期使用日期 20280921A1353"
    )

    assert extracted.production_date == "2025-09-21"
    assert extracted.batch_no == "A1353"


def test_batch_report_extracts_direct_production_date_from_slash_or_batch_label(
    monkeypatch,
):
    monkeypatch.setattr(batch_report_extraction, "_extract_with_llm", lambda _text: None)

    extracted, _metadata = extract_batch_report_fields(
        "生产日期/或批号 20250921 "
        "生产日期和保质期或生产批号和限期使用日期 20280921A1353"
    )

    assert extracted.production_date == "2025-09-21"
    assert extracted.batch_no == "A1353"


def test_batch_report_does_not_promote_composite_expiry_to_production_date(
    monkeypatch,
):
    monkeypatch.setattr(
        batch_report_extraction,
        "_extract_with_llm",
        lambda _text: {
            "production_date": "2028-09-21",
            "batch_no": None,
            "product_name": "超能白桃苏打洗洁精",
            "producer_name": "纳爱斯集团有限公司",
        },
    )

    extracted, metadata = extract_batch_report_fields(
        "生产日期和保质期或生产批号和限期使用日期 20280921A1353"
    )

    assert extracted.production_date is None
    assert extracted.batch_no == "A1353"
    assert metadata["field_reconciliation"]["production_date"]["selected"] == "none"


def test_batch_report_does_not_extract_batch_number_from_composite_date_only(monkeypatch):
    monkeypatch.setattr(batch_report_extraction, "_extract_with_llm", lambda _text: None)

    extracted, _metadata = extract_batch_report_fields(
        "生产日期和保质期或生产批号和限期使用日期 20280921"
    )

    assert extracted.production_date is None
    assert extracted.batch_no is None


@pytest.mark.parametrize(
    "expiry_date",
    ["2028-09-21", "2028/09/21", "2028年09月21", "2028年09月21日"],
)
def test_batch_report_does_not_backtrack_composite_date_into_batch_number(
    monkeypatch,
    expiry_date,
):
    monkeypatch.setattr(batch_report_extraction, "_extract_with_llm", lambda _text: None)

    extracted, _metadata = extract_batch_report_fields(
        "生产日期和保质期或生产批号和限期使用日期 " + expiry_date
    )

    assert extracted.batch_no is None


def test_batch_report_does_not_read_use_by_field_after_empty_production_date(monkeypatch):
    monkeypatch.setattr(batch_report_extraction, "_extract_with_llm", lambda _text: None)
    extracted, _metadata = extract_batch_report_fields(
        """
        生产日期
        限期使用日期 20280921
        """
    )

    assert extracted.production_date is None


def test_qc_document_review_extracts_batch_report_from_remote_image_ocr(monkeypatch):
    image_buffer = BytesIO()
    Image.new("RGB", (80, 120), "white").save(image_buffer, format="PNG")

    class StubDownloader:
        calls = 0

        def download(self, file_url):
            self.calls += 1
            return RemoteDocument(
                source_url=file_url,
                content=image_buffer.getvalue(),
                file_type="png",
                mime_type="image/png",
                status_code=200,
                headers={"content-type": "image/png"},
            )

    class StubOcrAdapter:
        def extract_text(self, source):
            assert source.mime_type == "image/png"
            return {
                "text": (
                    "商品批次报告\n"
                    "厂名：纳爱斯集团有限公司\n"
                    "产品名称：超能白桃苏打洗洁精\n"
                    "生产日期/或批号 20250921\n"
                    "生产日期和保质期或生产批号和限期使用日期 20280921A1353"
                ),
                "metadata": {"provider": "stub_ocr", "status": "extracted"},
            }

    downloader = StubDownloader()
    monkeypatch.setattr(qc_document_workflow, "qc_document_remote_downloader", downloader)
    monkeypatch.setattr(qc_document_workflow, "qc_batch_report_file_adapter", StubOcrAdapter())

    result = ReviewService().review(
        ReviewInput(
            file={
                "file_uri": "https://files.example.test/batch-report.png",
                "file_name": "batch-report.png",
            },
            supplier_name="纳爱斯集团有限公司",
            supplier_credit_code="",
            declared_document_type="batch_report",
            source={
                "vendor_name": "纳爱斯集团有限公司",
                "sku_name": "超能白桃苏打洗洁精",
                "production_date": "2025-09-21",
            },
        ),
        use_case_name="qc_document_review",
    )

    fields = result.skill_result["extracted_fields"]
    assert fields["product_name"] == "超能白桃苏打洗洁精"
    assert fields["production_date"] == "2025-09-21"
    assert fields["batch_no"] == "A1353"
    assert result.skill_result["document_input"]["input_type"] == "remote_image_ocr"
    assert result.skill_result["extraction_metadata"]["ocr_fallback"]["provider"] == (
        "stub_ocr"
    )
    assert downloader.calls == 1


def test_qc_document_review_keeps_remote_image_ocr_failure_for_manual_review(
    monkeypatch,
):
    image_buffer = BytesIO()
    Image.new("RGB", (80, 120), "white").save(image_buffer, format="PNG")

    class StubDownloader:
        def download(self, file_url):
            return RemoteDocument(
                source_url=file_url,
                content=image_buffer.getvalue(),
                file_type="png",
                mime_type="image/png",
                status_code=200,
                headers={"content-type": "image/png"},
            )

    class FailedOcrAdapter:
        def extract_text(self, _source):
            return {
                "text": "",
                "metadata": {
                    "provider": "stub_ocr",
                    "status": "failed",
                    "error_code": "OCR_FAILED",
                },
            }

    monkeypatch.setattr(qc_document_workflow, "qc_document_remote_downloader", StubDownloader())
    monkeypatch.setattr(
        qc_document_workflow,
        "qc_batch_report_file_adapter",
        FailedOcrAdapter(),
    )

    result = ReviewService().review(
        ReviewInput(
            file={
                "file_uri": "https://files.example.test/batch-report.png",
                "file_name": "batch-report.png",
            },
            supplier_name="纳爱斯集团有限公司",
            supplier_credit_code="",
            declared_document_type="batch_report",
        ),
        use_case_name="qc_document_review",
    )

    assert result.status == "PENDING_MANUAL_REVIEW"
    assert result.needs_manual_review is True
    assert result.skill_result["document_input"]["input_type"] == (
        "remote_image_ocr_failed"
    )
    assert result.skill_result["extracted_fields"]["product_name"] is None
    assert result.skill_result["extraction_metadata"]["ocr_fallback"]["error_code"] == (
        "OCR_FAILED"
    )


def test_qc_document_review_routes_remote_image_limit_to_manual_review(
    monkeypatch,
):
    image_buffer = BytesIO()
    Image.new("RGB", (80, 120), "white").save(image_buffer, format="PNG")

    class StubDownloader:
        def download(self, file_url):
            return RemoteDocument(
                source_url=file_url,
                content=image_buffer.getvalue(),
                file_type="png",
                mime_type="image/png",
                status_code=200,
                headers={"content-type": "image/png"},
            )

    class UnexpectedOcrAdapter:
        def extract_text(self, _source):
            raise AssertionError("超限图片不应调用 OCR")

    monkeypatch.setenv("BUSINESS_LICENSE_MAX_IMAGE_PIXELS", "100")
    monkeypatch.setattr(qc_document_workflow, "qc_document_remote_downloader", StubDownloader())
    monkeypatch.setattr(
        qc_document_workflow,
        "qc_batch_report_file_adapter",
        UnexpectedOcrAdapter(),
    )

    result = ReviewService().review(
        ReviewInput(
            file={
                "file_uri": "https://files.example.test/batch-report.png",
                "file_name": "batch-report.png",
            },
            supplier_name="纳爱斯集团有限公司",
            supplier_credit_code="",
            declared_document_type="batch_report",
        ),
        use_case_name="qc_document_review",
    )

    assert result.status == "PENDING_MANUAL_REVIEW"
    assert result.needs_manual_review is True
    assert result.skill_result["document_input"]["input_type"] == "remote_input_limit"
    assert result.skill_result["extraction_metadata"]["ocr_fallback"] == {
        "status": "limit_error",
        "error_code": "DOCUMENT_IMAGE_TOO_LARGE",
        "error_message": "营业执照图片分辨率超过限制",
    }
