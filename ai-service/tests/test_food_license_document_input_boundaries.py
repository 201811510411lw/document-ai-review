from fastapi.testclient import TestClient

from app.main import app
from app.models import ReviewDocumentInput, ReviewInput, ReviewInputContext
from app.tools.remote_document import RemoteDocument
from app.use_cases.food_license.use_case import food_license_use_case
from app.workflows.food_license import nodes as food_license_nodes
from tests.pdf_helpers import write_blank_pdf_with_pages, write_minimal_pdf


FIELDS = {
    "document_type": "food_license",
    "subject_name": "成都示例食品有限公司",
    "credit_code": "91510100MA00000000",
    "license_no": "JY15101000000000",
    "business_items": ["预包装食品销售"],
    "valid_to": "2028-06-05",
}


class TrackingFileAdapter:
    def __init__(self, fields=None):
        self.fields = fields or FIELDS
        self.calls = []

    def extract_text(self, source):
        self.calls.append(source)
        return {
            "text": "",
            "structured_fields": self.fields,
            "metadata": {
                "implementation_status": "stub",
                "provider": "fake",
                "model": "fake-food-license-file-recognition",
            },
        }


def test_local_pdf_with_embedded_text_uses_llm_file_recognition(
    tmp_path,
    monkeypatch,
):
    pdf_path = tmp_path / "food-license.pdf"
    write_minimal_pdf(pdf_path, "PDF text must not be used")
    adapter = TrackingFileAdapter()
    monkeypatch.setattr(food_license_nodes, "food_license_file_adapter", adapter)

    result = food_license_use_case.review(_input_context(_file_input(pdf_path)))
    payload = result.model_dump(mode="json")

    assert adapter.calls[0].content.startswith(b"%PDF-")
    assert adapter.calls[0].mime_type == "application/pdf"
    assert result.needs_manual_review is False
    assert payload["skill_result"]["document_input"]["input_type"] == "pdf"
    assert payload["skill_result"]["extracted_fields"]["license_no"] == "JY15101000000000"
    assert "pdf_loader" not in payload["skill_result"]["extraction_metadata"]


def test_local_file_path_alias_uses_llm_file_recognition(tmp_path, monkeypatch):
    pdf_path = tmp_path / "food-license-alias.pdf"
    write_minimal_pdf(pdf_path, "PDF text must not be used")
    adapter = TrackingFileAdapter()
    monkeypatch.setattr(food_license_nodes, "food_license_file_adapter", adapter)

    result = food_license_use_case.review(
        _input_context(
            ReviewDocumentInput(
                file_path=str(pdf_path),
                file_name="food-license-alias.pdf",
                mime_type="application/pdf",
                document_format="pdf",
            )
        )
    )

    assert adapter.calls[0].content.startswith(b"%PDF-")
    assert result.skill_result["document_input"]["input_type"] == "pdf"
    assert result.skill_result["extracted_fields"]["license_no"] == "JY15101000000000"


def test_local_png_file_uses_llm_file_recognition(tmp_path, monkeypatch):
    image_path = tmp_path / "food-license.png"
    image_path.write_bytes(b"fake-png-bytes")
    adapter = TrackingFileAdapter()
    monkeypatch.setattr(food_license_nodes, "food_license_file_adapter", adapter)

    result = food_license_use_case.review(
        _input_context(
            ReviewDocumentInput(
                local_path=str(image_path),
                file_name="food-license.png",
                mime_type="image/png",
                document_format="png",
            )
        )
    )

    assert adapter.calls[0].content == b"fake-png-bytes"
    assert adapter.calls[0].mime_type == "image/png"
    assert result.skill_result["document_input"]["input_type"] == "image"
    assert result.skill_result["extracted_fields"]["license_no"] == "JY15101000000000"


def test_local_jpeg_file_uses_llm_file_recognition(tmp_path, monkeypatch):
    image_path = tmp_path / "food-license.jpeg"
    image_path.write_bytes(b"fake-jpeg-bytes")
    adapter = TrackingFileAdapter()
    monkeypatch.setattr(food_license_nodes, "food_license_file_adapter", adapter)

    result = food_license_use_case.review(
        _input_context(
            ReviewDocumentInput(
                local_path=str(image_path),
                file_name="food-license.jpeg",
                mime_type="image/jpeg",
                document_format="jpeg",
            )
        )
    )

    assert adapter.calls[0].content == b"fake-jpeg-bytes"
    assert adapter.calls[0].mime_type == "image/jpeg"
    assert result.skill_result["document_input"]["input_type"] == "image"
    assert result.skill_result["document_input"]["document_format"] == "jpeg"


def test_remote_pdf_download_uses_llm_file_recognition(monkeypatch):
    adapter = TrackingFileAdapter()
    monkeypatch.setattr(food_license_nodes, "food_license_file_adapter", adapter)
    from pathlib import Path
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
        temp_pdf_path = Path(temp_file.name)
    write_minimal_pdf(temp_pdf_path, "PDF text must not be used")
    pdf_content = temp_pdf_path.read_bytes()

    class StubDownloader:
        def download(self, file_url):
            return RemoteDocument(
                source_url=file_url,
                content=pdf_content,
                file_type="pdf",
                mime_type="application/pdf",
                status_code=200,
                headers={"content-type": "application/pdf"},
            )

    monkeypatch.setattr(
        food_license_nodes,
        "food_license_remote_downloader",
        StubDownloader(),
    )

    result = food_license_use_case.review(
        _input_context(
            ReviewDocumentInput(
                file_uri="https://files.example.test/food-license.pdf",
                file_name="food-license.pdf",
            )
        )
    )
    payload = result.model_dump(mode="json")

    assert adapter.calls[0].content == pdf_content
    assert payload["skill_result"]["document_input"]["input_type"] == "pdf"
    assert payload["skill_result"]["extraction_metadata"]["remote_document"] == {
        "status_code": 200,
        "file_type": "pdf",
        "mime_type": "application/pdf",
        "needs_llm_file_recognition": True,
    }


def test_api_rejects_missing_local_pdf_with_stable_error(tmp_path):
    client = TestClient(app)

    response = client.post(
        "/api/v1/food-license/reviews",
        json={
            "file": {
                "local_path": str(tmp_path / "missing.pdf"),
                "file_name": "missing.pdf",
                "mime_type": "application/pdf",
                "document_format": "pdf",
            },
            "supplier_name": "成都示例食品有限公司",
            "supplier_credit_code": "91510100MA00000000",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "LOCAL_PDF_NOT_FOUND",
        "message": "file.local_path 指向的 PDF 文件不存在",
    }


def test_api_rejects_pdf_over_page_limit(tmp_path, monkeypatch):
    pdf_path = tmp_path / "too-many-pages.pdf"
    write_blank_pdf_with_pages(pdf_path, 2)
    monkeypatch.setenv("BUSINESS_LICENSE_MAX_PDF_PAGES", "1")
    client = TestClient(app)

    response = client.post(
        "/api/v1/food-license/reviews",
        json={
            "file": {
                "local_path": str(pdf_path),
                "file_name": "too-many-pages.pdf",
                "mime_type": "application/pdf",
                "document_format": "pdf",
            },
            "supplier_name": "成都示例食品有限公司",
            "supplier_credit_code": "91510100MA00000000",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "DOCUMENT_PDF_TOO_MANY_PAGES",
        "message": "营业执照 PDF 页数超过限制",
    }


def test_api_rejects_empty_document_input_with_stable_error():
    client = TestClient(app)

    response = client.post(
        "/api/v1/food-license/reviews",
        json={
            "supplier_name": "成都示例食品有限公司",
            "supplier_credit_code": "91510100MA00000000",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "EMPTY_DOCUMENT_INPUT",
        "message": "file.local_path 或 file.file_uri 至少提供一个",
    }


def test_api_rejects_text_input_with_stable_error(tmp_path):
    pdf_path = tmp_path / "food-license.pdf"
    write_minimal_pdf(pdf_path, "PDF text must not be used")
    client = TestClient(app)

    response = client.post(
        "/api/v1/food-license/reviews",
        json={
            "ocr_text": "食品经营许可证",
            "file": {
                "local_path": str(pdf_path),
                "file_name": "food-license.pdf",
                "mime_type": "application/pdf",
                "document_format": "pdf",
            },
            "supplier_name": "成都示例食品有限公司",
            "supplier_credit_code": "91510100MA00000000",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "UNSUPPORTED_TEXT_DOCUMENT_INPUT",
        "message": "食品许可证审核不支持 ocr_text 或 file.stub_text，请提供 PDF/JPG/JPEG/PNG 文件",
    }


def _input_context(file_input):
    return ReviewInputContext(
        task_id="review-task-file-boundary",
        input=ReviewInput(
            file=file_input,
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_license",
        ),
        skill_name="food_license",
        skill_version="v1",
        ruleset_version="food-license-rules-v1",
    )


def _file_input(pdf_path):
    return ReviewDocumentInput(
        local_path=str(pdf_path),
        file_name="food-license.pdf",
        mime_type="application/pdf",
        document_format="pdf",
    )
