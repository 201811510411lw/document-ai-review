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

    monkeypatch.setenv("BUSINESS_LICENSE_FAKE_VISION_JSON", _business_license_json())
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
        "document_format": "png",
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
    rule_metadata = payload["skill_result"]["source_evidence"][
        "skill_rule_review_metadata"
    ]
    assert rule_metadata["status_label"] == "已审核"
    assert rule_metadata["risk_level_label"] == "无风险"


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
        "source": "llm_file_extractor",
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
                "text": "",
                "structured_fields": _business_license_fields(),
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
        "message": "file.local_path 或 file.file_uri 至少提供一个",
    }


def test_business_license_review_rejects_text_and_file_input(tmp_path):
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
        "code": "UNSUPPORTED_TEXT_DOCUMENT_INPUT",
        "message": "营业执照审核不支持 ocr_text 或 file.stub_text，请提供 PDF/JPG/JPEG/PNG 文件",
    }


def test_business_license_review_rejects_text_only_input():
    client = TestClient(app)

    response = client.post(
        "/api/v1/business-license/reviews",
        json={
            "ocr_text": _business_license_text(),
            "supplier_name": "成都示例商贸有限公司",
            "supplier_credit_code": "91510100MA0000000X",
            "declared_document_type": "business_license",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "UNSUPPORTED_TEXT_DOCUMENT_INPUT",
        "message": "营业执照审核不支持 ocr_text 或 file.stub_text，请提供 PDF/JPG/JPEG/PNG 文件",
    }


def test_business_license_review_uses_llm_file_extractor_for_text_pdf(tmp_path, monkeypatch):
    pdf_path = tmp_path / "business-license.pdf"
    write_minimal_pdf(pdf_path, _business_license_text())
    monkeypatch.setenv("BUSINESS_LICENSE_FAKE_VISION_JSON", _business_license_json())
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
    assert "pdf_loader" not in payload["skill_result"]["extraction_metadata"]
    assert (
        payload["skill_result"]["extraction_metadata"]["llm_file_extractor"][
            "implementation_status"
        ]
        == "fake"
    )


def test_business_license_text_only_model_output_does_not_bypass_structured_fields(
    tmp_path,
    monkeypatch,
):
    pdf_path = tmp_path / "business-license.pdf"
    write_minimal_pdf(pdf_path, _business_license_text())

    class TextOnlyFileAdapter:
        def extract_text(self, source):
            return {
                "text": _business_license_text(),
                "metadata": {"implementation_status": "stub"},
            }

    monkeypatch.setattr(
        business_license_nodes,
        "business_license_vision_adapter",
        TextOnlyFileAdapter(),
    )

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
    assert payload["status"] == "PENDING_MANUAL_REVIEW"
    assert payload["needs_manual_review"] is True
    assert payload["skill_result"]["extracted_fields"]["subject_name"] is None
    assert payload["skill_result"]["extraction_metadata"]["structured_extraction"] == {
        "source": "llm_file_extractor",
        "schema": "BusinessLicenseExtractedFields",
        "status": "missing_structured_fields",
    }


def test_business_license_hallucinated_fields_route_high_risk_manual_review(
    tmp_path,
    monkeypatch,
):
    pdf_path = tmp_path / "liaoji-business-license.pdf"
    write_minimal_pdf(pdf_path, _business_license_text())
    monkeypatch.setenv(
        "BUSINESS_LICENSE_FAKE_VISION_JSON",
        """
        {
          "document_type": "business_license",
          "subject_name": "会唐县唐咖甲醇甲醇批发厂",
          "credit_code": "92130123MA6UUU68N",
          "business_address": "陕西市道江区新城甲醇甲醇批发厂",
          "legal_person": null,
          "established_date": "2020-11-11",
          "valid_to": "长期",
          "source_page": 1,
          "subject_name_evidence": "名称 会唐县唐咖甲醇甲醇批发厂",
          "credit_code_evidence": "统一社会信用代码 92130123MA6UUU68N"
        }
        """,
    )
    monkeypatch.delenv("BUSINESS_LICENSE_FAKE_VISION_TEXT", raising=False)

    client = TestClient(app)
    response = client.post(
        "/api/v1/business-license/reviews",
        json={
            "file": {
                "local_path": str(pdf_path),
                "file_name": "廖记食品有限责任公司-营业执照&法人身份证.pdf",
                "mime_type": "application/pdf",
                "document_format": "pdf",
            },
            "supplier_name": "廖记食品有限责任公司",
            "supplier_credit_code": "91510132MA6AULU68M",
            "declared_document_type": "business_license",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "PENDING_MANUAL_REVIEW"
    assert payload["risk_level"] == "HIGH"
    assert payload["needs_manual_review"] is True
    assert "主体名称与来源信息不一致" in payload["manual_review"]["reasons"]
    assert "统一社会信用代码格式异常" in payload["manual_review"]["reasons"]
    assert (
        payload["skill_result"]["extracted_fields"]["subject_name"]
        == "会唐县唐咖甲醇甲醇批发厂"
    )
    credit_rule = next(
        item
        for item in payload["rule_results"]
        if item["rule_code"] == "BUSINESS_LICENSE_CREDIT_CODE_MATCH"
    )
    assert credit_rule["passed"] is False
    assert credit_rule["details"] == {
        "field": "credit_code",
        "expected": "91510132MA6AULU68M",
        "actual": "92130123MA6UUU68N",
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
    assert payload["skill_result"]["extraction_metadata"]["llm_file_extractor"] == {
        "implementation_status": "fake",
        "provider": "fake",
        "model": "fake-business-license-vision",
        "error_code": "VISION_EXTRACTOR_NOT_CONFIGURED",
    }
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
    monkeypatch.setenv("BUSINESS_LICENSE_FAKE_VISION_JSON", _business_license_json())
    monkeypatch.delenv("BUSINESS_LICENSE_FAKE_VISION_TEXT", raising=False)

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
        "needs_llm_file_recognition": True,
    }


def test_business_license_review_accepts_remote_jpeg_file(monkeypatch):
    monkeypatch.setenv("BUSINESS_LICENSE_FAKE_VISION_JSON", _business_license_json())
    monkeypatch.delenv("BUSINESS_LICENSE_FAKE_VISION_TEXT", raising=False)

    class StubDownloader:
        def download(self, file_url):
            return RemoteDocument(
                source_url=file_url,
                content=b"fake-remote-jpeg",
                file_type="jpeg",
                mime_type="image/jpeg",
                status_code=200,
                headers={"content-type": "image/jpeg"},
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
                "file_uri": "https://files.example.test/business-license.jpeg",
                "file_name": "business-license.jpeg",
            },
            "supplier_name": "成都示例商贸有限公司",
            "supplier_credit_code": "91510100MA0000000X",
            "declared_document_type": "business_license",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "REVIEWED"
    assert payload["skill_result"]["document_input"]["input_type"] == "image"
    assert payload["skill_result"]["document_input"]["document_format"] == "jpeg"


def test_business_license_review_uses_llm_file_extractor_for_remote_pdf(tmp_path, monkeypatch):
    pdf_path = tmp_path / "business-license.pdf"
    write_minimal_pdf(pdf_path, _business_license_text())
    monkeypatch.setenv("BUSINESS_LICENSE_FAKE_VISION_JSON", _business_license_json())
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
        "needs_llm_file_recognition": True,
    }
    assert "pdf_loader" not in payload["skill_result"]["extraction_metadata"]
    assert (
        payload["skill_result"]["extraction_metadata"]["llm_file_extractor"][
            "implementation_status"
        ]
        == "fake"
    )


def test_business_license_scanned_local_pdf_uses_vision_extractor(
    tmp_path,
    monkeypatch,
):
    pdf_path = tmp_path / "business-license-scan.pdf"
    write_blank_pdf(pdf_path)
    monkeypatch.setenv("BUSINESS_LICENSE_FAKE_VISION_JSON", _business_license_json())
    monkeypatch.delenv("BUSINESS_LICENSE_FAKE_VISION_TEXT", raising=False)

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
    assert "pdf_loader" not in payload["skill_result"]["extraction_metadata"]
    assert (
        payload["skill_result"]["extraction_metadata"]["llm_file_extractor"][
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
                "text": "",
                "structured_fields": _business_license_fields(),
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


def _business_license_json() -> str:
    return """
    {
      "document_type": "business_license",
      "subject_name": "成都示例商贸有限公司",
      "credit_code": "91510100MA0000000X",
      "business_address": "成都市高新区天府大道 1 号",
      "legal_person": "张三",
      "valid_from": "2020-01-02",
      "valid_to": "2030-01-01"
    }
    """


def _business_license_fields() -> dict:
    return {
        "document_type": "business_license",
        "subject_name": "成都示例商贸有限公司",
        "credit_code": "91510100MA0000000X",
        "business_address": "成都市高新区天府大道 1 号",
        "legal_person": "张三",
        "valid_from": "2020-01-02",
        "valid_to": "2030-01-01",
    }
