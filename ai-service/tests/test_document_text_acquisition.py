from app.models import ReviewDocumentInput, ReviewInput
from app.tools.document_text_acquisition import acquire_document_text
from app.tools.remote_document import RemoteDocument, RemoteDocumentDownloadError
from tests.pdf_helpers import write_blank_pdf, write_blank_pdf_with_pages, write_minimal_pdf


class StubDownloader:
    def __init__(self, document=None, error=None):
        self.document = document
        self.error = error
        self.urls = []

    def download(self, file_url):
        self.urls.append(file_url)
        if self.error:
            raise self.error
        return self.document


def test_acquire_document_text_uses_ocr_text_without_downloading():
    downloader = StubDownloader()

    result = acquire_document_text(
        ReviewInput(
            ocr_text="产品检验报告\n样品名称：鲜切蛋糕",
            supplier_name="广东乃一口食品有限公司",
            supplier_credit_code="",
            declared_document_type="product_report",
        ),
        downloader=downloader,
    )

    assert result.document_text == "产品检验报告\n样品名称：鲜切蛋糕"
    assert result.document_input["input_type"] == "ocr_text"
    assert result.extraction_metadata == {}
    assert downloader.urls == []


def test_acquire_document_text_extracts_text_layer_from_remote_pdf(tmp_path):
    pdf_path = tmp_path / "product-report.pdf"
    write_minimal_pdf(
        pdf_path,
        "产品检验报告\n报告编号：A2260511467101001C\n样品名称：鲜切蛋糕(蓝莓风味)",
    )
    downloader = StubDownloader(
        RemoteDocument(
            source_url="https://files.example.test/product-report.pdf",
            content=pdf_path.read_bytes(),
            file_type="pdf",
            mime_type="application/pdf",
            status_code=200,
            headers={"content-type": "application/pdf"},
        )
    )

    result = acquire_document_text(
        ReviewInput(
            file=ReviewDocumentInput(
                file_uri="https://files.example.test/product-report.pdf",
                file_name="product-report.pdf",
            ),
            supplier_name="广东乃一口食品有限公司",
            supplier_credit_code="",
            declared_document_type="product_report",
        ),
        downloader=downloader,
    )

    assert "报告编号：A2260511467101001C" in result.document_text
    assert "样品名称：鲜切蛋糕(蓝莓风味)" in result.document_text
    assert result.document_input == {
        "input_type": "remote_pdf_text",
        "file_name": "product-report.pdf",
        "mime_type": "application/pdf",
        "document_format": "pdf",
        "source_url": "https://files.example.test/product-report.pdf",
    }
    assert result.extraction_metadata["remote_document"] == {
        "status_code": 200,
        "file_type": "pdf",
        "mime_type": "application/pdf",
    }
    assert result.extraction_metadata["pdf_text_extractor"]["page_count"] == 1
    assert result.extraction_metadata["pdf_text_extractor"]["pages_with_text"] == 1
    assert result.extraction_metadata["pdf_text_extractor"]["status"] == "extracted"


def test_acquire_document_text_marks_blank_remote_pdf_for_ocr_fallback(tmp_path):
    pdf_path = tmp_path / "blank-product-report.pdf"
    write_blank_pdf(pdf_path)
    downloader = StubDownloader(
        RemoteDocument(
            source_url="https://files.example.test/blank-product-report.pdf",
            content=pdf_path.read_bytes(),
            file_type="pdf",
            mime_type="application/pdf",
            status_code=200,
            headers={"content-type": "application/pdf"},
        )
    )

    result = acquire_document_text(
        ReviewInput(
            file=ReviewDocumentInput(
                file_uri="https://files.example.test/blank-product-report.pdf",
                file_name="blank-product-report.pdf",
            ),
            supplier_name="广东乃一口食品有限公司",
            supplier_credit_code="",
            declared_document_type="product_report",
        ),
        downloader=downloader,
    )

    assert result.document_text == ""
    assert result.document_input["input_type"] == "remote_pdf_empty_text"
    assert result.extraction_metadata["pdf_text_extractor"]["status"] == "empty_text_layer"
    assert result.extraction_metadata["pdf_text_extractor"]["needs_ocr_fallback"] is True


def test_acquire_document_text_returns_remote_error_metadata():
    downloader = StubDownloader(
        error=RemoteDocumentDownloadError(
            "REMOTE_DOCUMENT_HTTP_403",
            "远程文件下载返回 HTTP 403",
            status_code=403,
            source_url="https://files.example.test/forbidden.pdf",
        )
    )

    result = acquire_document_text(
        ReviewInput(
            file=ReviewDocumentInput(
                file_uri="https://files.example.test/forbidden.pdf",
                file_name="forbidden.pdf",
            ),
            supplier_name="广东乃一口食品有限公司",
            supplier_credit_code="",
            declared_document_type="product_report",
        ),
        downloader=downloader,
    )

    assert result.document_text == ""
    assert result.document_input["input_type"] == "remote_error"
    assert result.extraction_metadata["remote_document_error"] == {
        "code": "REMOTE_DOCUMENT_HTTP_403",
        "source_url": "https://files.example.test/forbidden.pdf",
        "status_code": 403,
    }


def test_acquire_document_text_allows_multi_page_product_report_pdf(tmp_path):
    pdf_path = tmp_path / "five-page-product-report.pdf"
    write_blank_pdf_with_pages(pdf_path, 5)
    downloader = StubDownloader(
        RemoteDocument(
            source_url="https://files.example.test/five-page-product-report.pdf",
            content=pdf_path.read_bytes(),
            file_type="pdf",
            mime_type="application/pdf",
            status_code=200,
            headers={"content-type": "application/pdf"},
        )
    )

    result = acquire_document_text(
        ReviewInput(
            file=ReviewDocumentInput(
                file_uri="https://files.example.test/five-page-product-report.pdf",
                file_name="five-page-product-report.pdf",
            ),
            supplier_name="广东乃一口食品有限公司",
            supplier_credit_code="",
            declared_document_type="product_report",
        ),
        downloader=downloader,
    )

    assert result.document_input["input_type"] == "remote_pdf_empty_text"
    assert result.extraction_metadata["pdf_text_extractor"]["page_count"] == 5
    assert result.extraction_metadata["pdf_text_extractor"]["status"] == "empty_text_layer"


def test_acquire_document_text_routes_remote_image_to_ocr_fallback():
    downloader = StubDownloader(
        RemoteDocument(
            source_url="https://files.example.test/product-report.jpg",
            content=b"fake-jpg",
            file_type="jpg",
            mime_type="image/jpeg",
            status_code=200,
            headers={"content-type": "image/jpeg"},
        )
    )

    result = acquire_document_text(
        ReviewInput(
            file=ReviewDocumentInput(
                file_uri="https://files.example.test/product-report.jpg",
                file_name="product-report.jpg",
            ),
            supplier_name="广东乃一口食品有限公司",
            supplier_credit_code="",
            declared_document_type="product_report",
        ),
        downloader=downloader,
    )

    assert result.document_text == ""
    assert result.document_input["input_type"] == "remote_unsupported_text"
    assert result.document_input["document_format"] == "jpg"
    assert result.extraction_metadata["remote_document"]["needs_ocr_fallback"] is True
