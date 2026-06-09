from fastapi.testclient import TestClient

from app.api.food_license_reviews import get_review_service
from app.main import app
from app.repositories.sqlite_review_repository import SQLiteReviewRepository
from app.services.review_service import ReviewService


def _client_with_temp_review_service(tmp_path):
    repository = SQLiteReviewRepository(tmp_path / "reviews.sqlite3")
    service = ReviewService(repository=repository)
    app.dependency_overrides[get_review_service] = lambda: service
    return TestClient(app)


def _clear_overrides():
    app.dependency_overrides.clear()


def test_food_license_ocr_review_persists_result_and_can_be_queried(tmp_path):
    client = _client_with_temp_review_service(tmp_path)
    try:
        response = client.post(
            "/api/v1/food-license/reviews",
            json={
                "ocr_text": "食品经营许可证\n经营者名称：成都示例食品有限公司\n统一社会信用代码：91510100MA00000000\n许可证编号：JY15101000000000\n经营项目：预包装食品销售、散装食品销售\n有效期至：2099-01-01",
                "supplier_name": "成都示例食品有限公司",
                "supplier_credit_code": "91510100MA00000000",
                "supplier_address": "成都市示例区示例路 100 号",
                "declared_document_type": "food_license",
            },
        )

        assert response.status_code == 200
        created = response.json()
        task_id = created["task_id"]
        assert created["status"] == "REVIEWED"
        assert created["risk_level"] == "NONE"
        assert created["needs_manual_review"] is False
        assert "extracted_fields" not in created
        assert created["skill_result"]["extracted_fields"]["license_no"] == "JY15101000000000"
        assert created["skill_result"]["normalized_fields"]["credit_code"] == "91510100MA00000000"
        assert created["rule_results"]
        assert all(rule_result["passed"] for rule_result in created["rule_results"])

        query_response = client.get(f"/api/v1/food-license/reviews/{task_id}")

        assert query_response.status_code == 200
        queried = query_response.json()
        assert queried == created
    finally:
        _clear_overrides()


def test_food_license_review_detects_rule_failures_and_allows_manual_review(tmp_path):
    client = _client_with_temp_review_service(tmp_path)
    try:
        response = client.post(
            "/api/v1/food-license/reviews",
            json={
                "ocr_text": "食品经营许可证\n经营者名称：成都示例食品有限公司\n统一社会信用代码：91510100MA00000000\n许可证编号：JY15101000000000\n经营项目：预包装食品销售\n有效期至：2025-01-01",
                "supplier_name": "成都示例食品有限公司",
                "supplier_credit_code": "91510100MA99999999",
                "declared_document_type": "food_license",
            },
        )

        assert response.status_code == 200
        created = response.json()
        assert created["status"] == "PENDING_MANUAL_REVIEW"
        assert created["risk_level"] == "HIGH"
        assert created["needs_manual_review"] is True
        assert created["manual_review"]["status"] == "PENDING"
        failed_rule_codes = {
            rule_result["rule_code"]
            for rule_result in created["rule_results"]
            if not rule_result["passed"]
        }
        assert "CREDIT_CODE_MATCH" in failed_rule_codes
        assert "FOOD_LICENSE_EXPIRED" in failed_rule_codes

        manual_response = client.post(
            f"/api/v1/food-license/reviews/{created['task_id']}/manual-review",
            json={
                "action": "REJECT",
                "reviewer": "reviewer-001",
                "comment": "证照已过期且信用代码不一致。",
            },
        )

        assert manual_response.status_code == 200
        reviewed = manual_response.json()
        assert reviewed["status"] == "MANUAL_REVIEWED"
        assert reviewed["needs_manual_review"] is False
        assert reviewed["manual_review"]["status"] == "COMPLETED"
        assert reviewed["manual_review"]["action"] == "REJECT"
        assert reviewed["manual_review"]["reviewer"] == "reviewer-001"

        query_response = client.get(f"/api/v1/food-license/reviews/{created['task_id']}")

        assert query_response.status_code == 200
        assert query_response.json()["manual_review"]["status"] == "COMPLETED"
    finally:
        _clear_overrides()


def test_food_license_file_review_uses_stub_ocr_and_can_be_queried(tmp_path):
    client = _client_with_temp_review_service(tmp_path)
    try:
        response = client.post(
            "/api/v1/food-license/reviews",
            json={
                "supplier_name": "成都示例食品有限公司",
                "supplier_credit_code": "91510100MA00000000",
                "declared_document_type": "food_license",
                "file": {
                    "filename": "food-license.pdf",
                    "content_type": "application/pdf",
                    "content_base64": "ZmFrZS1wZGY=",
                },
                "source": {"input_type": "pdf"},
                "options": {
                    "stub_ocr_text": "食品经营许可证\n经营者名称：成都示例食品有限公司\n统一社会信用代码：91510100MA00000000\n许可证编号：JY15101000000000\n经营项目：预包装食品销售\n有效期至：2099-01-01"
                },
            },
        )

        assert response.status_code == 200
        created = response.json()
        assert created["status"] == "REVIEWED"
        assert created["needs_manual_review"] is False
        assert created["skill_result"]["extracted_fields"]["license_no"] == "JY15101000000000"
        assert created["skill_result"]["extraction_metadata"]["extraction_mode"] == "regex_only"
        assert "extraction_metadata" not in created
        assert "extracted_fields" not in created

        query_response = client.get(f"/api/v1/food-license/reviews/{created['task_id']}")

        assert query_response.status_code == 200
        assert query_response.json() == created
    finally:
        _clear_overrides()


def test_unknown_review_task_returns_404(tmp_path):
    client = _client_with_temp_review_service(tmp_path)
    try:
        response = client.get("/api/v1/food-license/reviews/review-task-missing")

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "REVIEW_TASK_NOT_FOUND"
    finally:
        _clear_overrides()


def test_manual_review_action_rejects_unknown_action(tmp_path):
    client = _client_with_temp_review_service(tmp_path)
    try:
        create_response = client.post(
            "/api/v1/food-license/reviews",
            json={
                "ocr_text": "食品经营许可证\n经营者名称：成都示例食品有限公司\n统一社会信用代码：91510100MA00000000\n许可证编号：JY15101000000000\n经营项目：预包装食品销售\n有效期至：2025-01-01",
                "supplier_name": "成都示例食品有限公司",
                "supplier_credit_code": "91510100MA99999999",
                "declared_document_type": "food_license",
            },
        )

        response = client.post(
            f"/api/v1/food-license/reviews/{create_response.json()['task_id']}/manual-review",
            json={
                "action": "ARCHIVE",
                "reviewer": "reviewer-001",
            },
        )

        assert response.status_code == 422
        error = response.json()["detail"][0]
        assert error["loc"] == ["body", "action"]
    finally:
        _clear_overrides()
