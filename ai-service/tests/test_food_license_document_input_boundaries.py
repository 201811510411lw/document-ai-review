from fastapi.testclient import TestClient

from app.main import app
from app.models import RiskLevel, ReviewDocumentInput, ReviewInput, ReviewInputContext
from app.use_cases.food_license.skill import food_license_use_case
from app.tools.document_loader import LocalPdfDocumentLoader
from app.workflows.food_license import nodes as food_license_nodes


FOOD_LICENSE_TEXT = (
    "食品经营许可证\n"
    "经营者名称：成都示例食品有限公司\n"
    "统一社会信用代码：91510100MA00000000\n"
    "许可证编号：JY15101000000000\n"
    "经营项目：预包装食品销售、散装食品销售\n"
    "有效期至：2028年06月05日"
)


def write_minimal_pdf(path, text: str) -> None:
    text_stream = _pdf_text_stream(text)
    unicode_map = _pdf_unicode_map(text)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 8 0 R >>"
        ),
        (
            b"<< /Type /Font /Subtype /Type0 /BaseFont /Helvetica "
            b"/Encoding /Identity-H /DescendantFonts [5 0 R] /ToUnicode 6 0 R >>"
        ),
        (
            b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /Helvetica "
            b"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) "
            b"/Supplement 0 >> /FontDescriptor 7 0 R >>"
        ),
        _pdf_stream_object(unicode_map),
        (
            b"<< /Type /FontDescriptor /FontName /Helvetica /Flags 4 "
            b"/FontBBox [0 -200 1000 900] /ItalicAngle 0 /Ascent 800 "
            b"/Descent -200 /CapHeight 700 /StemV 80 >>"
        ),
        _pdf_stream_object(text_stream),
    ]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{index} 0 obj\n".encode("ascii"))
        content.extend(obj)
        content.extend(b"\nendobj\n")
    xref_offset = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    content.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    path.write_bytes(content)


def write_blank_pdf(path) -> None:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>",
    ]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{index} 0 obj\n".encode("ascii"))
        content.extend(obj)
        content.extend(b"\nendobj\n")
    xref_offset = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    content.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    path.write_bytes(content)


def _pdf_stream_object(data: str) -> bytes:
    raw = data.encode("utf-8")
    return (
        b"<< /Length "
        + str(len(raw)).encode("ascii")
        + b" >>\nstream\n"
        + raw
        + b"\nendstream"
    )


def _pdf_text_stream(text: str) -> str:
    lines = ["BT /F1 12 Tf 72 720 Td 14 TL"]
    for index, line in enumerate(text.splitlines()):
        if index:
            lines.append("T*")
        lines.append(f"<{''.join(f'{ord(char):04X}' for char in line)}> Tj")
    lines.append("ET")
    return "\n".join(lines)


def _pdf_unicode_map(text: str) -> str:
    entries = [
        f"<{ord(char):04X}> <{ord(char):04X}>"
        for char in sorted(set(text) - {"\n"})
    ]
    return "\n".join(
        [
            "/CIDInit /ProcSet findresource begin",
            "12 dict begin",
            "begincmap",
            "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
            "/CMapName /Adobe-Identity-UCS def",
            "/CMapType 2 def",
            "1 begincodespacerange",
            "<0000> <FFFF>",
            "endcodespacerange",
            f"{len(entries)} beginbfchar",
            *entries,
            "endbfchar",
            "endcmap",
            "CMapName currentdict /CMap defineresource pop",
            "end",
            "end",
        ]
    )


def test_ocr_text_input_stays_compatible():
    result = food_license_use_case.review(
        ReviewInputContext(
            task_id="review-task-ocr-text",
            input=ReviewInput(
                ocr_text=f"  {FOOD_LICENSE_TEXT}  ",
                supplier_name="成都示例食品有限公司",
                supplier_credit_code="91510100MA00000000",
                declared_document_type="food_license",
            ),
            skill_name="food_license",
            skill_version="v1",
            ruleset_version="food-license-rules-v1",
        )
    )

    payload = result.model_dump(mode="json")

    assert result.needs_manual_review is False
    assert payload["skill_result"]["document_input"]["input_type"] == "ocr_text"
    assert payload["skill_result"]["extracted_fields"]["license_no"] == "JY15101000000000"


def test_pdf_metadata_with_stub_text_runs_review_flow_without_file_access():
    result = food_license_use_case.review(
        ReviewInputContext(
            task_id="review-task-pdf",
            input=ReviewInput(
                file=ReviewDocumentInput(
                    file_uri="s3://private-bucket/licenses/example.pdf",
                    file_name="example.pdf",
                    mime_type="application/pdf",
                    document_format="pdf",
                    stub_text=FOOD_LICENSE_TEXT,
                ),
                supplier_name="成都示例食品有限公司",
                supplier_credit_code="91510100MA00000000",
                declared_document_type="food_license",
            ),
            skill_name="food_license",
            skill_version="v1",
            ruleset_version="food-license-rules-v1",
        )
    )

    payload = result.model_dump(mode="json")

    assert result.needs_manual_review is False
    assert payload["skill_result"]["document_input"] == {
        "input_type": "pdf",
        "file_name": "example.pdf",
        "mime_type": "application/pdf",
        "document_format": "pdf",
    }
    assert payload["skill_result"]["extracted_fields"]["license_no"] == "JY15101000000000"


def test_pdf_local_path_input_reads_pdf_text_and_completes_review_result(tmp_path):
    pdf_path = tmp_path / "food-license.pdf"
    write_minimal_pdf(pdf_path, FOOD_LICENSE_TEXT)

    client = TestClient(app)
    response = client.post(
        "/api/v1/food-license/reviews",
        json={
            "file": {
                "local_path": str(pdf_path),
                "file_name": "food-license.pdf",
                "mime_type": "application/pdf",
                "document_format": "pdf",
            },
            "supplier_name": "成都示例食品有限公司",
            "supplier_credit_code": "91510100MA00000000",
            "declared_document_type": "food_license",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "REVIEWED"
    assert payload["risk_level"] == "NONE"
    assert payload["needs_manual_review"] is False
    assert payload["skill_result"]["document_input"] == {
        "input_type": "pdf",
        "file_name": "food-license.pdf",
        "mime_type": "application/pdf",
        "document_format": "pdf",
    }
    assert payload["skill_result"]["extracted_fields"]["license_no"] == "JY15101000000000"
    assert payload["skill_result"]["extraction_metadata"]["pdf_loader"] == {
        "implementation_status": "implemented",
        "needs_ocr": False,
        "source": "local_path",
    }
    assert [rule_result["rule_code"] for rule_result in payload["rule_results"]] == [
        "FOOD_LICENSE_RULE_ENGINE_STUB",
        "FOOD_LICENSE_TYPE_MATCH",
        "FOOD_LICENSE_SUBJECT_NAME_MATCH",
        "FOOD_LICENSE_CREDIT_CODE_MATCH",
        "FOOD_LICENSE_VALIDITY_PERIOD",
    ]
    assert all(rule_result["passed"] is True for rule_result in payload["rule_results"])


def test_pdf_local_path_missing_file_returns_stable_error(tmp_path):
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


def test_pdf_local_path_without_embedded_text_marks_needs_ocr_and_skips_llm(
    tmp_path,
    monkeypatch,
):
    pdf_path = tmp_path / "blank-food-license.pdf"
    write_blank_pdf(pdf_path)
    llm_calls = []

    class TrackingLlmAdapter:
        def complete_missing_fields(self, **kwargs):
            llm_calls.append(kwargs)
            return {}

    monkeypatch.setattr(
        food_license_nodes,
        "food_license_llm_adapter",
        TrackingLlmAdapter(),
    )

    result = food_license_use_case.review(
        ReviewInputContext(
            task_id="review-task-blank-local-pdf",
            input=ReviewInput(
                file=ReviewDocumentInput(
                    local_path=str(pdf_path),
                    file_name="blank-food-license.pdf",
                    mime_type="application/pdf",
                    document_format="pdf",
                ),
                supplier_name="成都示例食品有限公司",
                supplier_credit_code="91510100MA00000000",
                declared_document_type="food_license",
            ),
            skill_name="food_license",
            skill_version="v1",
            ruleset_version="food-license-rules-v1",
        )
    )

    assert result.skill_result.document_input.input_type == "pdf"
    assert result.skill_result.extraction_metadata["pdf_loader"]["needs_ocr"] is True
    assert result.skill_result.extraction_metadata["llm_used"] is False
    assert result.needs_manual_review is True
    assert result.manual_review.reasons == ["文档类型无法识别，需要人工复核"]
    assert llm_calls == []


def test_pdf_file_path_alias_reads_pdf_text(tmp_path):
    pdf_path = tmp_path / "food-license-alias.pdf"
    write_minimal_pdf(pdf_path, FOOD_LICENSE_TEXT)

    result = food_license_use_case.review(
        ReviewInputContext(
            task_id="review-task-file-path",
            input=ReviewInput(
                file=ReviewDocumentInput(
                    file_path=str(pdf_path),
                    file_name="food-license-alias.pdf",
                    mime_type="application/pdf",
                    document_format="pdf",
                ),
                supplier_name="成都示例食品有限公司",
                supplier_credit_code="91510100MA00000000",
                declared_document_type="food_license",
            ),
            skill_name="food_license",
            skill_version="v1",
            ruleset_version="food-license-rules-v1",
        )
    )

    assert result.skill_result.document_input.input_type == "pdf"
    assert result.skill_result.extracted_fields.license_no == "JY15101000000000"


def test_local_pdf_loader_does_not_access_network_or_llm_and_does_not_decide_risk(
    tmp_path,
    monkeypatch,
):
    pdf_path = tmp_path / "food-license.pdf"
    write_minimal_pdf(pdf_path, FOOD_LICENSE_TEXT)
    network_calls = []
    llm_calls = []

    def fake_create_connection(*args, **kwargs):
        network_calls.append((args, kwargs))
        raise AssertionError("network access is not allowed")

    class TrackingLlmAdapter:
        def complete_missing_fields(self, **kwargs):
            llm_calls.append(kwargs)
            return {}

    monkeypatch.setattr("socket.create_connection", fake_create_connection)
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_llm_adapter",
        TrackingLlmAdapter(),
    )

    loader_result = LocalPdfDocumentLoader().load(
        ReviewDocumentInput(
            local_path=str(pdf_path),
            file_name="food-license.pdf",
            mime_type="application/pdf",
            document_format="pdf",
        )
    )
    review_result = food_license_use_case.review(
        ReviewInputContext(
            task_id="review-task-local-pdf",
            input=ReviewInput(
                file=ReviewDocumentInput(
                    local_path=str(pdf_path),
                    file_name="food-license.pdf",
                    mime_type="application/pdf",
                    document_format="pdf",
                ),
                supplier_name="成都示例食品有限公司",
                supplier_credit_code="91510100MA00000000",
                declared_document_type="food_license",
            ),
            skill_name="food_license",
            skill_version="v1",
            ruleset_version="food-license-rules-v1",
        )
    )

    assert loader_result["text"].strip()
    assert "risk_level" not in loader_result["metadata"]
    assert network_calls == []
    assert llm_calls == []
    assert review_result.risk_level == RiskLevel.NONE


def test_file_input_uses_stub_document_loader(monkeypatch):
    calls = []

    class StubLoader:
        def load(self, source):
            calls.append(source)
            return {
                "text": FOOD_LICENSE_TEXT,
                "metadata": {
                    "file_name": source.file_name,
                    "mime_type": source.mime_type,
                    "document_format": source.document_format,
                },
            }

    monkeypatch.setattr(food_license_nodes, "food_license_document_loader", StubLoader())

    result = food_license_use_case.review(
        ReviewInputContext(
            task_id="review-task-loader",
            input=ReviewInput(
                file=ReviewDocumentInput(
                    file_uri="s3://private-bucket/licenses/example.pdf",
                    file_name="example.pdf",
                    mime_type="application/pdf",
                    document_format="pdf",
                ),
                supplier_name="成都示例食品有限公司",
                supplier_credit_code="91510100MA00000000",
                declared_document_type="food_license",
            ),
            skill_name="food_license",
            skill_version="v1",
            ruleset_version="food-license-rules-v1",
        )
    )

    assert len(calls) == 1
    assert calls[0].file_uri == "s3://private-bucket/licenses/example.pdf"
    assert result.skill_result.extracted_fields.license_no == "JY15101000000000"


def test_file_input_can_use_stub_ocr_adapter_when_loader_has_no_text(monkeypatch):
    class MetadataOnlyLoader:
        def load(self, source):
            return {
                "text": "",
                "metadata": {
                    "file_name": source.file_name,
                    "mime_type": source.mime_type,
                    "document_format": source.document_format,
                },
            }

    monkeypatch.setattr(
        food_license_nodes,
        "food_license_document_loader",
        MetadataOnlyLoader(),
    )

    result = food_license_use_case.review(
        ReviewInputContext(
            task_id="review-task-stub-ocr",
            input=ReviewInput(
                file=ReviewDocumentInput(
                    file_uri="s3://private-bucket/licenses/example.pdf",
                    file_name="example.pdf",
                    mime_type="application/pdf",
                    document_format="pdf",
                    stub_text=FOOD_LICENSE_TEXT,
                ),
                supplier_name="成都示例食品有限公司",
                supplier_credit_code="91510100MA00000000",
                declared_document_type="food_license",
            ),
            skill_name="food_license",
            skill_version="v1",
            ruleset_version="food-license-rules-v1",
        )
    )

    assert result.skill_result.document_input.input_type == "pdf"
    assert result.skill_result.extracted_fields.license_no == "JY15101000000000"


def test_image_metadata_with_stub_text_runs_review_flow_without_file_access():
    result = food_license_use_case.review(
        ReviewInputContext(
            task_id="review-task-image",
            input=ReviewInput(
                file=ReviewDocumentInput(
                    file_uri="s3://private-bucket/licenses/example.png",
                    file_name="example.png",
                    mime_type="image/png",
                    document_format="image",
                    stub_text=FOOD_LICENSE_TEXT,
                ),
                supplier_name="成都示例食品有限公司",
                supplier_credit_code="91510100MA00000000",
                declared_document_type="food_license",
            ),
            skill_name="food_license",
            skill_version="v1",
            ruleset_version="food-license-rules-v1",
        )
    )

    payload = result.model_dump(mode="json")

    assert result.needs_manual_review is False
    assert payload["skill_result"]["document_input"]["input_type"] == "image"
    assert payload["skill_result"]["document_input"]["mime_type"] == "image/png"
    assert payload["skill_result"]["extracted_fields"]["license_no"] == "JY15101000000000"


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
        "message": "ocr_text、file.stub_text 或 file.local_path 至少提供一个",
    }


def test_api_rejects_ambiguous_text_and_file_input_with_stable_error():
    client = TestClient(app)

    response = client.post(
        "/api/v1/food-license/reviews",
        json={
            "ocr_text": FOOD_LICENSE_TEXT,
            "file": {
                "file_uri": "s3://private-bucket/licenses/example.pdf",
                "file_name": "example.pdf",
                "mime_type": "application/pdf",
                "document_format": "pdf",
            },
            "supplier_name": "成都示例食品有限公司",
            "supplier_credit_code": "91510100MA00000000",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "AMBIGUOUS_DOCUMENT_INPUT",
        "message": "ocr_text 和文件输入只能二选一",
    }
