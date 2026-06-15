from datetime import datetime

from fastapi.testclient import TestClient
from uuid import UUID

from app.api.food_license_reviews import get_review_service
from app.main import app
from app.models import ReviewResult
from app.workflows.food_license import nodes as food_license_nodes
from tests.pdf_helpers import write_minimal_pdf


FOOD_LICENSE_JSON = """
{
  "document_type": "food_license",
  "subject_name": "成都示例食品有限公司",
  "credit_code": "91510100MA00000000",
  "license_no": "JY15101000000000",
  "business_items": ["预包装食品销售", "散装食品销售"],
  "valid_to": "2028-06-05"
}
"""


def test_food_license_review_accepts_local_pdf_with_fake_llm_file_extractor(tmp_path, monkeypatch):
    pdf_path = tmp_path / "food-license.pdf"
    write_minimal_pdf(pdf_path, "this embedded text must not be used")

    class StubFileAdapter:
        def extract_text(self, source):
            return {
                "text": "",
                "structured_fields": {
                    "document_type": "food_license",
                    "subject_name": "成都示例食品有限公司",
                    "credit_code": "91510100MA00000000",
                    "license_no": "JY15101000000000",
                    "business_items": ["预包装食品销售", "散装食品销售"],
                    "valid_to": "2028-06-05",
                },
                "metadata": {
                    "implementation_status": "fake",
                    "provider": "fake",
                    "model": "fake-food-license-file-recognition",
                },
            }

    monkeypatch.setattr(food_license_nodes, "food_license_file_adapter", StubFileAdapter())

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
            "supplier_address": "成都市示例区示例路 100 号",
            "declared_document_type": "food_license",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert list(payload.keys()) == [
        "task_id",
        "use_case_name",
        "use_case_version",
        "skill_name",
        "skill_version",
        "ruleset_version",
        "capability_names",
        "document_type",
        "status",
        "risk_level",
        "needs_manual_review",
        "rule_results",
        "summary",
        "manual_review",
        "audit_events",
        "created_at",
        "updated_at",
        "skill_result",
    ]
    assert _is_review_task_uuid(payload["task_id"])
    assert payload["use_case_name"] == "food_license"
    assert payload["use_case_version"] == "v1"
    assert payload["skill_name"] == "food_license"
    assert payload["skill_version"] == "v1"
    assert payload["ruleset_version"] == "food-license-rules-v1"
    assert payload["capability_names"] == ["food_license"]
    assert payload["document_type"] == "food_license"
    assert payload["status"] == "REVIEWED"
    assert payload["risk_level"] == "NONE"
    assert payload["needs_manual_review"] is False
    assert payload["manual_review"]["status"] == "NOT_REQUIRED"
    assert isinstance(payload["rule_results"], list)
    assert [rule_result["rule_code"] for rule_result in payload["rule_results"]] == [
        "FOOD_LICENSE_RULE_ENGINE_STUB",
        "FOOD_LICENSE_TYPE_MATCH",
        "FOOD_LICENSE_SUBJECT_NAME_MATCH",
        "FOOD_LICENSE_CREDIT_CODE_MATCH",
        "FOOD_LICENSE_VALIDITY_PERIOD",
    ]
    assert isinstance(payload["audit_events"], list)
    assert datetime.fromisoformat(payload["created_at"]).tzinfo is not None
    assert datetime.fromisoformat(payload["updated_at"]).tzinfo is not None

    assert "extracted_fields" not in payload
    assert "normalized_fields" not in payload
    assert "document_classification" not in payload
    assert payload["skill_result"]["document_classification"]["document_type"] == "food_license"
    assert payload["skill_result"]["document_input"]["input_type"] == "pdf"
    assert payload["skill_result"]["extracted_fields"]["license_no"] == "JY15101000000000"
    assert payload["skill_result"]["normalized_fields"]["license_no"] == "JY15101000000000"
    assert "pdf_loader" not in payload["skill_result"]["extraction_metadata"]
    assert (
        payload["skill_result"]["extraction_metadata"]["llm_file_extractor"][
            "implementation_status"
        ]
        == "fake"
    )


def test_food_license_review_rejects_ocr_text_with_stable_error():
    client = TestClient(app)

    response = client.post(
        "/api/v1/food-license/reviews",
        json={
            "ocr_text": "食品经营许可证",
            "supplier_name": "成都示例食品有限公司",
            "supplier_credit_code": "91510100MA00000000",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "UNSUPPORTED_TEXT_DOCUMENT_INPUT",
        "message": "食品许可证审核不支持 ocr_text 或 file.stub_text，请提供 PDF/JPG/JPEG/PNG 文件",
    }


def test_food_license_review_rejects_empty_ocr_text_with_stable_error():
    client = TestClient(app)

    response = client.post(
        "/api/v1/food-license/reviews",
        json={
            "ocr_text": "   ",
            "supplier_name": "成都示例食品有限公司",
            "supplier_credit_code": "91510100MA00000000",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "EMPTY_DOCUMENT_INPUT",
        "message": "file.local_path 或 file.file_uri 至少提供一个",
    }


def test_food_license_review_requires_supplier_identity_fields():
    client = TestClient(app)

    response = client.post(
        "/api/v1/food-license/reviews",
        json={
            "ocr_text": "食品经营许可证",
        },
    )

    assert response.status_code == 422
    errors = response.json()["detail"]
    missing_fields = {tuple(error["loc"]) for error in errors}
    assert ("body", "supplier_name") in missing_fields
    assert ("body", "supplier_credit_code") in missing_fields


def test_food_license_review_route_calls_review_service_boundary():
    client = TestClient(app)
    calls = []

    class StubReviewService:
        def review_food_license(self, review_input):
            calls.append(review_input)
            return ReviewResult.model_validate(
                {
                    "task_id": "review-task-stub",
                    "use_case_name": "food_license",
                    "use_case_version": "v1",
                    "skill_name": "food_license",
                    "skill_version": "v1",
                    "ruleset_version": "food-license-rules-v1",
                    "capability_names": ["food_license"],
                    "document_type": "food_license",
                    "status": "REVIEWED",
                    "risk_level": "NONE",
                    "needs_manual_review": False,
                    "rule_results": [],
                    "summary": "stub",
                    "manual_review": {"status": "NOT_REQUIRED"},
                    "audit_events": [],
                    "created_at": "2026-06-08T14:30:00+00:00",
                    "updated_at": "2026-06-08T14:30:00+00:00",
                    "skill_result": {},
                }
            )

    app.dependency_overrides[get_review_service] = lambda: StubReviewService()
    try:
        response = client.post(
            "/api/v1/food-license/reviews",
            json={
                "file": {
                    "local_path": "/tmp/food-license.png",
                    "file_name": "food-license.png",
                    "mime_type": "image/png",
                },
                "supplier_name": "成都示例食品有限公司",
                "supplier_credit_code": "91510100MA00000000",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["task_id"] == "review-task-stub"
    assert len(calls) == 1
    assert calls[0].supplier_name == "成都示例食品有限公司"


def _is_review_task_uuid(task_id: str) -> bool:
    prefix = "review-task-"
    if not task_id.startswith(prefix):
        return False
    try:
        UUID(task_id.removeprefix(prefix))
    except ValueError:
        return False
    return True
