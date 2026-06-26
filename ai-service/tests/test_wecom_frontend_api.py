from fastapi.testclient import TestClient

from app.api.business_license_reviews import get_review_read_repository
from app.main import app
from app.repositories.review_result_repository import MySQLReviewResultRepository
from tests.business_license_helpers import business_license_auth_headers, business_license_repository
from tests.mysql_repository_stub import install_mysql_repository_stub
from tests.test_business_license_review_query_api import _save_review


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


def test_wecom_frontend_review_list_maps_current_business_license_reviews(tmp_path, monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-wecom-frontend.pdf",
        supplier_name="成都示例商贸有限公司",
        supplier_credit_code="91510100MA0000000X",
        source_record_id="SRM-CERT-LEGACY",
        attachment_ref_id="ATT-LEGACY",
        source_url="https://files.example.test/business-wecom-frontend.pdf",
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        "/api/review/list",
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["stats"]["total"] == 1
    assert payload["records"][0]["company_name"] == "成都示例商贸有限公司"
    assert payload["records"][0]["license_type"] == "营业执照"
    assert payload["records"][0]["id"]


def test_wecom_frontend_auth_profile_accepts_current_bearer_token(monkeypatch):
    client = TestClient(app)
    headers = business_license_auth_headers(client, monkeypatch)

    response = client.get("/auth/profile", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "reviewer",
        "name": "审核员",
        "is_admin": True,
    }


def test_wecom_frontend_confirm_review_writes_manual_review_decision(tmp_path, monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-wecom-confirm.pdf",
        supplier_name="上海云岚供应链管理有限公司",
        supplier_credit_code="91310115MA1K00002Q",
        extracted_credit_code="91310115MA1K00002R",
        source_record_id="SRM-CERT-WECOM-CONFIRM",
        attachment_ref_id="ATT-WECOM-CONFIRM",
        source_url="https://files.example.test/business-wecom-confirm.pdf",
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.post(
        f"/api/review/{result.task_id}/confirm",
        json={"comment": "已核对原始营业执照。"},
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    detail = repository.get_business_license_snapshot(result.task_id)
    assert detail["review_status"] == "MANUAL_REVIEWED"
    assert detail["manual_review_decision"] == "approved"
    assert detail["manual_review_comment"] == "已核对原始营业执照。"


def test_wecom_frontend_flagged_filter_returns_all_high_risk_records(tmp_path, monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-wecom-ok.pdf",
        supplier_name="成都示例商贸有限公司",
        supplier_credit_code="91510100MA0000000X",
        source_record_id="SRM-CERT-WECOM-OK",
        attachment_ref_id="ATT-WECOM-OK",
        source_url="https://files.example.test/business-wecom-ok.pdf",
    )
    pending_high_risk = _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-wecom-pending-high-risk.pdf",
        supplier_name="上海云岚供应链管理有限公司",
        supplier_credit_code="91310115MA1K00002Q",
        extracted_credit_code="91310115MA1K00002R",
        source_record_id="SRM-CERT-WECOM-PENDING-HIGH-RISK",
        attachment_ref_id="ATT-WECOM-PENDING-HIGH-RISK",
        source_url="https://files.example.test/business-wecom-pending-high-risk.pdf",
    )
    manually_flagged = _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-wecom-manually-flagged.pdf",
        supplier_name="北京示例科技有限公司",
        supplier_credit_code="91110101MA0000000Q",
        extracted_credit_code="91110101MA0000000R",
        source_record_id="SRM-CERT-WECOM-MANUALLY-FLAGGED",
        attachment_ref_id="ATT-WECOM-MANUALLY-FLAGGED",
        source_url="https://files.example.test/business-wecom-manually-flagged.pdf",
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)
    headers = business_license_auth_headers(client, monkeypatch)

    flag_response = client.post(
        f"/api/review/{manually_flagged.task_id}/flag",
        json={"comment": "识别结果异常。"},
        headers=headers,
    )
    response = client.get(
        "/api/review/list",
        params={"review_status": "flagged"},
        headers=headers,
    )

    assert flag_response.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert payload["stats"] == {
        "total": 3,
        "pending": 1,
        "confirmed": 2,
        "flagged": 2,
    }
    assert {record["id"] for record in payload["records"]} == {
        pending_high_risk.task_id,
        manually_flagged.task_id,
    }
    assert {record["review_status"] for record in payload["records"]} == {"flagged"}


def test_wecom_frontend_accepts_demo_token_for_vue_demo_mode(monkeypatch):
    client = TestClient(app)

    profile_response = client.get("/auth/profile", headers={"Authorization": "Bearer demo-token"})
    stats_response = client.get(
        "/api/dashboard/stats",
        headers={"Authorization": "Bearer demo-token"},
    )

    assert profile_response.status_code == 200
    assert profile_response.json() == {
        "user_id": "DemoUser",
        "name": "演示用户",
        "is_admin": True,
    }
    assert stats_response.status_code == 200
    assert "data" in stats_response.json()


def _repository() -> MySQLReviewResultRepository:
    return business_license_repository()
