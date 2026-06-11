from fastapi.testclient import TestClient

from app.main import app
from tests.pdf_helpers import write_blank_pdf, write_blank_pdf_with_pages, write_minimal_pdf
from app.tools.remote_document import RemoteDocument
from app.workflows.business_license import nodes as business_license_nodes


def test_business_license_review_accepts_image_file_with_fake_vision_extractor(
    tmp_path,
    monkeypatch,
):
    image_path = tmp_path / "business-license.png"
    image_path.write_bytes(b"fake-image-bytes")

    monkeypatch.setenv("BUSINESS_LICENSE_FAKE_VISION_TEXT", _business_license_text())

    client = TestClient(app)
    response = client.post(
        "/api/v1/business-license/reviews",
        json={
            "file": {
                "local_path": str(image_path),
                "file_name": "business-license.png",
                "mime_type": "image/png",
                "document_format": "image",
            },
            "supplier_name": "成都示例商贸有限公司",
            "supplier_credit_code": "91510100MA0000000X",
            "declared_document_type": "business_license",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["use_case_name"] == "business_license"
    assert payload["document_type"] == "business_license"
    assert payload["status"] == "REVIEWED"
    assert payload["risk_level"] == "NONE"
    assert payload["needs_manual_review"] is False
    assert payload["manual_review"]["status"] == "NOT_REQUIRED"
    assert payload["skill_result"]["document_input"] == {
        "input_type": "image",
        "file_name": "business-license.png",
        "mime_type": "image/png",
        "document_format": "image",
        "source_url": None,
    }
    assert (
        payload["skill_result"]["extracted_fields"]["subject_name"]
        == "成都示例商贸有限公司"
    )
    assert (
        payload["skill_result"]["extraction_metadata"]["vision_extractor"][
            "implementation_status"
        ]
        == "fake"
    )


def test_business_license_review_accepts_structured_fields_from_vision_adapter(
    tmp_path,
    monkeypatch,
):
    image_path = tmp_path / "business-license.png"
    image_path.write_bytes(b"fake-image-bytes")
    monkeypatch.setenv(
        "BUSINESS_LICENSE_FAKE_VISION_JSON",
        """
        {
          "document_type": "business_license",
          "subject_name": "成都示例商贸有限公司",
          "credit_code": "91510100MA0000000X",
          "business_address": "成都市高新区天府大道 1 号",
          "legal_person": "张三",
          "valid_from": "2020-01-02",
          "valid_to": "2030-01-01"
        }
        """,
    )
    monkeypatch.delenv("BUSINESS_LICENSE_FAKE_VISION_TEXT", raising=False)

    client = TestClient(app)
    response = client.post(
        "/api/v1/business-license/reviews",
        json={
            "file": {
                "local_path": str(image_path),
                "file_name": "business-license.png",
                "mime_type": "image/png",
                "document_format": "image",
            },
            "supplier_name": "成都示例商贸有限公司",
            "supplier_credit_code": "91510100MA0000000X",
            "declared_document_type": "business_license",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "REVIEWED"
    assert payload["risk_level"] == "NONE"
    assert payload["skill_result"]["document_classification"]["document_type"] == "business_license"
    assert (
        payload["skill_result"]["extracted_fields"]["subject_name"]
        == "成都示例商贸有限公司"
    )
    assert payload["skill_result"]["extraction_metadata"]["structured_extraction"] == {
        "source": "vision_adapter",
        "schema": "BusinessLicenseExtractedFields",
    }


def test_business_license_local_image_passes_file_bytes_to_vision_adapter(
    tmp_path,
    monkeypatch,
):
    image_path = tmp_path / "business-license.png"
    image_path.write_bytes(b"fake-image-bytes")
    seen = {}

    class StubVisionAdapter:
        def extract_text(self, source):
            seen["content"] = source.content
            seen["mime_type"] = source.mime_type
            return {
                "text": _business_license_text(),
                "metadata": {"implementation_status": "stub"},
            }

    monkeypatch.setattr(
        business_license_nodes,
        "business_license_vision_adapter",
        StubVisionAdapter(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/business-license/reviews",
        json={
            "file": {
                "local_path": str(image_path),
                "file_name": "business-license.png",
                "mime_type": "image/png",
                "document_format": "image",
            },
            "supplier_name": "成都示例商贸有限公司",
            "supplier_credit_code": "91510100MA0000000X",
            "declared_document_type": "business_license",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REVIEWED"
    assert seen == {"content": b"fake-image-bytes", "mime_type": "image/png"}


def test_business_license_review_rejects_empty_document_input():
    client = TestClient(app)

    response = client.post(
        "/api/v1/business-license/reviews",
        json={
            "ocr_text": "   ",
            "supplier_name": "成都示例商贸有限公司",
            "supplier_credit_code": "91510100MA0000000X",
            "declared_document_type": "business_license",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "EMPTY_DOCUMENT_INPUT",
        "message": "ocr_text、file.stub_text、file.local_path 或 file.file_uri 至少提供一个",
    }


def test_business_license_review_rejects_ambiguous_text_and_file_input(tmp_path):
    image_path = tmp_path / "business-license.png"
    image_path.write_bytes(b"fake-image-bytes")
    client = TestClient(app)

    response = client.post(
        "/api/v1/business-license/reviews",
        json={
            "ocr_text": _business_license_text(),
            "file": {
                "local_path": str(image_path),
                "file_name": "business-license.png",
                "mime_type": "image/png",
                "document_format": "image",
            },
            "supplier_name": "成都示例商贸有限公司",
            "supplier_credit_code": "91510100MA0000000X",
            "declared_document_type": "business_license",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "AMBIGUOUS_DOCUMENT_INPUT",
        "message": "ocr_text 和文件输入只能二选一",
    }


def test_business_license_review_reads_text_from_local_pdf(tmp_path, monkeypatch):
    pdf_path = tmp_path / "business-license.pdf"
    write_minimal_pdf(pdf_path, _business_license_text())
    monkeypatch.delenv("BUSINESS_LICENSE_FAKE_VISION_TEXT", raising=False)

    client = TestClient(app)
    response = client.post(
        "/api/v1/business-license/reviews",
        json={
            "file": {
                "local_path": str(pdf_path),
                "file_name": "business-license.pdf",
                "mime_type": "application/pdf",
                "document_format": "pdf",
            },
            "supplier_name": "成都示例商贸有限公司",
            "supplier_credit_code": "91510100MA0000000X",
            "declared_document_type": "business_license",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "REVIEWED"
    assert payload["risk_level"] == "NONE"
    assert payload["needs_manual_review"] is False
    assert payload["skill_result"]["document_input"] == {
        "input_type": "pdf",
        "file_name": "business-license.pdf",
        "mime_type": "application/pdf",
        "document_format": "pdf",
        "source_url": None,
    }
    assert payload["skill_result"]["extraction_metadata"]["pdf_loader"] == {
        "implementation_status": "implemented",
        "needs_ocr": False,
        "source": "local_path",
    }


def test_business_license_image_without_vision_configuration_routes_manual_review(
    tmp_path,
    monkeypatch,
):
    image_path = tmp_path / "business-license.png"
    image_path.write_bytes(b"fake-image-bytes")
    monkeypatch.delenv("BUSINESS_LICENSE_FAKE_VISION_TEXT", raising=False)

    client = TestClient(app)
    response = client.post(
        "/api/v1/business-license/reviews",
        json={
            "file": {
                "local_path": str(image_path),
                "file_name": "business-license.png",
                "mime_type": "image/png",
                "document_format": "image",
            },
            "supplier_name": "成都示例商贸有限公司",
            "supplier_credit_code": "91510100MA0000000X",
            "declared_document_type": "business_license",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "PENDING_MANUAL_REVIEW"
    assert payload["risk_level"] == "HIGH"
    assert payload["needs_manual_review"] is True
    assert "视觉模型未配置或未返回文本" in payload["manual_review"]["reasons"]
    assert payload["skill_result"]["extraction_metadata"]["vision_extractor"] == {
        "implementation_status": "fake",
        "provider": "fake",
        "model": "fake-business-license-vision",
        "error_code": "VISION_EXTRACTOR_NOT_CONFIGURED",
    }


def test_business_license_missing_local_pdf_returns_stable_error(tmp_path):
    client = TestClient(app)

    response = client.post(
        "/api/v1/business-license/reviews",
        json={
            "file": {
                "local_path": str(tmp_path / "missing.pdf"),
                "file_name": "missing.pdf",
                "mime_type": "application/pdf",
                "document_format": "pdf",
            },
            "supplier_name": "成都示例商贸有限公司",
            "supplier_credit_code": "91510100MA0000000X",
            "declared_document_type": "business_license",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "LOCAL_PDF_NOT_FOUND",
        "message": "file.local_path 指向的 PDF 文件不存在",
    }


def test_business_license_rejects_local_image_over_size_limit(tmp_path, monkeypatch):
    image_path = tmp_path / "too-large.png"
    image_path.write_bytes(b"x" * 11)
    monkeypatch.setenv("BUSINESS_LICENSE_MAX_FILE_BYTES", "10")

    client = TestClient(app)
    response = client.post(
        "/api/v1/business-license/reviews",
        json={
            "file": {
                "local_path": str(image_path),
                "file_name": "too-large.png",
                "mime_type": "image/png",
                "document_format": "image",
            },
            "supplier_name": "成都示例商贸有限公司",
            "supplier_credit_code": "91510100MA0000000X",
            "declared_document_type": "business_license",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "DOCUMENT_FILE_TOO_LARGE",
        "message": "营业执照文件超过大小限制",
    }


def test_business_license_rejects_pdf_over_page_limit(tmp_path, monkeypatch):
    pdf_path = tmp_path / "too-many-pages.pdf"
    write_blank_pdf_with_pages(pdf_path, 2)
    monkeypatch.setenv("BUSINESS_LICENSE_MAX_PDF_PAGES", "1")

    client = TestClient(app)
    response = client.post(
        "/api/v1/business-license/reviews",
        json={
            "file": {
                "local_path": str(pdf_path),
                "file_name": "too-many-pages.pdf",
                "mime_type": "application/pdf",
                "document_format": "pdf",
            },
            "supplier_name": "成都示例商贸有限公司",
            "supplier_credit_code": "91510100MA0000000X",
            "declared_document_type": "business_license",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "DOCUMENT_PDF_TOO_MANY_PAGES",
        "message": "营业执照 PDF 页数超过限制",
    }


def test_business_license_rejects_image_over_pixel_limit(tmp_path, monkeypatch):
    from PIL import Image

    image_path = tmp_path / "too-many-pixels.png"
    Image.new("RGB", (4, 4), color="white").save(image_path)
    monkeypatch.setenv("BUSINESS_LICENSE_MAX_IMAGE_PIXELS", "15")

    client = TestClient(app)
    response = client.post(
        "/api/v1/business-license/reviews",
        json={
            "file": {
                "local_path": str(image_path),
                "file_name": "too-many-pixels.png",
                "mime_type": "image/png",
                "document_format": "image",
            },
            "supplier_name": "成都示例商贸有限公司",
            "supplier_credit_code": "91510100MA0000000X",
            "declared_document_type": "business_license",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "DOCUMENT_IMAGE_TOO_LARGE",
        "message": "营业执照图片分辨率超过限制",
    }


def test_business_license_review_accepts_remote_image_file(
    monkeypatch,
):
    monkeypatch.setenv("BUSINESS_LICENSE_FAKE_VISION_TEXT", _business_license_text())

    class StubDownloader:
        def download(self, file_url):
            return RemoteDocument(
                source_url=file_url,
                content=b"fake-remote-image",
                file_type="png",
                mime_type="image/png",
                status_code=200,
                headers={"content-type": "image/png"},
            )

    monkeypatch.setattr(
        business_license_nodes,
        "business_license_remote_downloader",
        StubDownloader(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/business-license/reviews",
        json={
            "file": {
                "file_uri": "https://files.example.test/business-license.png",
                "file_name": "business-license.png",
            },
            "supplier_name": "成都示例商贸有限公司",
            "supplier_credit_code": "91510100MA0000000X",
            "declared_document_type": "business_license",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "REVIEWED"
    assert payload["risk_level"] == "NONE"
    assert payload["skill_result"]["document_input"] == {
        "input_type": "image",
        "file_name": "business-license.png",
        "mime_type": "image/png",
        "document_format": "png",
        "source_url": "https://files.example.test/business-license.png",
    }
    assert payload["skill_result"]["extraction_metadata"]["remote_document"] == {
        "status_code": 200,
        "file_type": "png",
        "mime_type": "image/png",
        "needs_vision": True,
    }


def test_business_license_review_reads_text_from_remote_pdf(tmp_path, monkeypatch):
    pdf_path = tmp_path / "business-license.pdf"
    write_minimal_pdf(pdf_path, _business_license_text())
    monkeypatch.delenv("BUSINESS_LICENSE_FAKE_VISION_TEXT", raising=False)

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

    monkeypatch.setattr(
        business_license_nodes,
        "business_license_remote_downloader",
        StubDownloader(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/business-license/reviews",
        json={
            "file": {
                "file_uri": "https://files.example.test/business-license.pdf",
                "file_name": "business-license.pdf",
            },
            "supplier_name": "成都示例商贸有限公司",
            "supplier_credit_code": "91510100MA0000000X",
            "declared_document_type": "business_license",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "REVIEWED"
    assert payload["risk_level"] == "NONE"
    assert payload["skill_result"]["document_input"] == {
        "input_type": "pdf",
        "file_name": "business-license.pdf",
        "mime_type": "application/pdf",
        "document_format": "pdf",
        "source_url": "https://files.example.test/business-license.pdf",
    }
    assert payload["skill_result"]["extraction_metadata"]["remote_document"] == {
        "status_code": 200,
        "file_type": "pdf",
        "mime_type": "application/pdf",
    }
    assert payload["skill_result"]["extraction_metadata"]["pdf_loader"] == {
        "implementation_status": "implemented",
        "needs_ocr": False,
        "source": "remote_content",
    }


def test_business_license_scanned_local_pdf_uses_vision_extractor(
    tmp_path,
    monkeypatch,
):
    pdf_path = tmp_path / "business-license-scan.pdf"
    write_blank_pdf(pdf_path)
    monkeypatch.setenv("BUSINESS_LICENSE_FAKE_VISION_TEXT", _business_license_text())

    client = TestClient(app)
    response = client.post(
        "/api/v1/business-license/reviews",
        json={
            "file": {
                "local_path": str(pdf_path),
                "file_name": "business-license-scan.pdf",
                "mime_type": "application/pdf",
                "document_format": "pdf",
            },
            "supplier_name": "成都示例商贸有限公司",
            "supplier_credit_code": "91510100MA0000000X",
            "declared_document_type": "business_license",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "REVIEWED"
    assert payload["risk_level"] == "NONE"
    assert payload["skill_result"]["document_input"]["input_type"] == "pdf"
    assert payload["skill_result"]["extraction_metadata"]["pdf_loader"] == {
        "implementation_status": "implemented",
        "needs_ocr": True,
        "source": "local_path",
    }
    assert (
        payload["skill_result"]["extraction_metadata"]["vision_extractor"][
            "implementation_status"
        ]
        == "fake"
    )


def test_business_license_scanned_local_pdf_passes_pdf_bytes_to_vision_adapter(
    tmp_path,
    monkeypatch,
):
    pdf_path = tmp_path / "business-license-scan.pdf"
    write_blank_pdf(pdf_path)
    seen = {}

    class StubVisionAdapter:
        def extract_text(self, source):
            seen["content_prefix"] = source.content[:5]
            seen["mime_type"] = source.mime_type
            return {
                "text": _business_license_text(),
                "metadata": {"implementation_status": "stub"},
            }

    monkeypatch.setattr(
        business_license_nodes,
        "business_license_vision_adapter",
        StubVisionAdapter(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/business-license/reviews",
        json={
            "file": {
                "local_path": str(pdf_path),
                "file_name": "business-license-scan.pdf",
                "mime_type": "application/pdf",
                "document_format": "pdf",
            },
            "supplier_name": "成都示例商贸有限公司",
            "supplier_credit_code": "91510100MA0000000X",
            "declared_document_type": "business_license",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REVIEWED"
    assert seen == {"content_prefix": b"%PDF-", "mime_type": "application/pdf"}


def _business_license_text() -> str:
    return (
        "营业执照\n"
        "统一社会信用代码：91510100MA0000000X\n"
        "名称：成都示例商贸有限公司\n"
        "住所：成都市高新区天府大道 1 号\n"
        "法定代表人：张三\n"
        "营业期限：2020年01月02日至2030年01月01日\n"
    )
