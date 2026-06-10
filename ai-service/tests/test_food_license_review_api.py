from datetime import datetime

from fastapi.testclient import TestClient

from app.api.food_license_reviews import get_review_service
from app.main import app
from app.models import ReviewResult


def test_food_license_review_accepts_ocr_text_and_returns_review_result():
    client = TestClient(app)

    response = client.post(
        "/api/v1/food-license/reviews",
        json={
            "ocr_text": (
                "食品经营许可证\n"
                "经营者名称：成都示例食品有限公司\n"
                "统一社会信用代码：91510100MA00000000\n"
                "许可证编号：JY15101000000000\n"
                "经营项目：预包装食品销售、散装食品销售\n"
                "有效期至：2028年06月05日"
            ),
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
    assert payload["task_id"].startswith("review-task-")
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
    assert payload["skill_result"]["document_input"]["input_type"] == "ocr_text"
    assert payload["skill_result"]["extracted_fields"]["license_no"] == "JY15101000000000"
    assert payload["skill_result"]["normalized_fields"]["license_no"] == "JY15101000000000"


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
        "message": "ocr_text、file.stub_text 或 file.local_path 至少提供一个",
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
                "ocr_text": "食品经营许可证",
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
