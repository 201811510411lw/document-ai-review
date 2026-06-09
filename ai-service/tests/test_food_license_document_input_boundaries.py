from fastapi.testclient import TestClient

from app.main import app
from app.models import ReviewDocumentInput, ReviewInput, ReviewInputContext
from app.skills.food_license.skill import food_license_skill
from app.workflows.food_license import nodes as food_license_nodes


FOOD_LICENSE_TEXT = (
    "食品经营许可证\n"
    "经营者名称：成都示例食品有限公司\n"
    "统一社会信用代码：91510100MA00000000\n"
    "许可证编号：JY15101000000000\n"
    "经营项目：预包装食品销售、散装食品销售\n"
    "有效期至：2028年06月05日"
)


def test_ocr_text_input_stays_compatible():
    result = food_license_skill.review(
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
    result = food_license_skill.review(
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

    result = food_license_skill.review(
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

    result = food_license_skill.review(
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
    result = food_license_skill.review(
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
        "message": "ocr_text 或 file.stub_text 不能为空",
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
        "message": "ocr_text 和 file.stub_text 只能二选一",
    }
