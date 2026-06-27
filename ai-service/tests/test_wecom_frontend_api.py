import io
import json
import zipfile

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


def test_wecom_frontend_query_uses_real_qc_records(tmp_path, monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-query-real.pdf",
        supplier_name="成都真实查询有限公司",
        supplier_credit_code="91510100MAQUERY001",
        source_record_id="SRM-QUERY-001",
        attachment_ref_id="ATT-QUERY-001",
        source_url="https://files.example.test/business-query-real.pdf",
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.post(
        "/api/query",
        json={"keyword": "MAQUERY001"},
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["stats"]["found"] == 1
    assert payload["records"][0]["id"] == result.task_id
    assert payload["records"][0]["company_name"] == "成都真实查询有限公司"


def test_wecom_frontend_csv_upload_preview_queries_real_records(tmp_path, monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-query-csv.pdf",
        supplier_name="杭州批量查询有限公司",
        supplier_credit_code="91330100CSV000001",
        source_record_id="SRM-CSV-001",
        attachment_ref_id="ATT-CSV-001",
        source_url="https://files.example.test/business-query-csv.pdf",
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.post(
        "/api/query/excel",
        files={"file": ("query.csv", "公司名称\n杭州批量查询有限公司\n不存在公司\n", "text/csv")},
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["stats"] == {"found": 1, "expiring": 0, "expired": 1, "missing": 1}
    assert payload["columns"][0]["name"] == "公司名称"
    assert payload["records"][0]["company_name"] == "杭州批量查询有限公司"


def test_wecom_frontend_download_returns_traceable_zip(tmp_path, monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-download.pdf",
        supplier_name="深圳下载测试有限公司",
        supplier_credit_code="91440300DOWNLOAD",
        source_record_id="SRM-DOWNLOAD-001",
        attachment_ref_id="ATT-DOWNLOAD-001",
        source_url="https://files.example.test/business-download.pdf",
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.post(
        "/api/query/download",
        json={"ids": [result.task_id]},
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert b"manifest.json" in response.content


def test_wecom_frontend_admin_settings_and_license_types_are_real(tmp_path, monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-admin.pdf",
        supplier_name="北京系统管理有限公司",
        supplier_credit_code="91110100ADMIN001",
        source_record_id="SRM-ADMIN-001",
        attachment_ref_id="ATT-ADMIN-001",
        source_url="https://files.example.test/business-admin.pdf",
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)
    headers = business_license_auth_headers(client, monkeypatch)

    save_response = client.put("/api/admin/notify-users", json={"userIds": ["u1", "u1", "  ", "u2"]}, headers=headers)
    load_response = client.get("/api/admin/notify-users", headers=headers)
    types_response = client.get("/api/admin/license-types", headers=headers)

    assert save_response.status_code == 200
    assert save_response.json()["users"] == ["u1", "u2"]
    assert load_response.json()["users"] == ["u1", "u2"]
    assert types_response.status_code == 200
    assert any(item["document_type"] == "business_license" for item in types_response.json()["items"])
    assert all(item["readonly"] is True for item in types_response.json()["items"])


def test_wecom_frontend_records_can_be_ignored_without_deleting_review(tmp_path, monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-ignore.pdf",
        supplier_name="天津忽略记录有限公司",
        supplier_credit_code="91120100IGNORE01",
        source_record_id="SRM-IGNORE-001",
        attachment_ref_id="ATT-IGNORE-001",
        source_url="https://files.example.test/business-ignore.pdf",
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)
    headers = business_license_auth_headers(client, monkeypatch)

    before = client.get("/api/records", headers=headers)
    ignored = client.delete(f"/api/records/{result.task_id}", headers=headers)
    after = client.get("/api/records", headers=headers)

    assert before.json()["total"] == 1
    assert ignored.status_code == 200
    assert after.json()["total"] == 0
    assert repository.get_by_task_id(result.task_id) is not None


def test_wecom_frontend_import_preview_does_not_persist_silent_success(tmp_path, monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-import-preview.pdf",
        supplier_name="南京导入预览有限公司",
        supplier_credit_code="91320100IMPORT01",
        source_record_id="SRM-IMPORT-001",
        attachment_ref_id="ATT-IMPORT-001",
        source_url="https://files.example.test/business-import-preview.pdf",
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.post(
        "/api/admin/import/preview",
        files={"file": ("import.csv", "公司名称\n南京导入预览有限公司\n缺失供应商\n", "text/csv")},
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "preview_only"
    assert payload["success_count"] == 1
    assert payload["failure_count"] == 1
    assert payload["errors"] == [{"value": "缺失供应商", "reason": "当前审核结果中未找到匹配记录"}]


def test_wecom_frontend_query_reports_no_result_stats(monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.post(
        "/api/query",
        json={"keyword": "不存在公司"},
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    assert response.json() == {
        "records": [],
        "stats": {"found": 0, "expiring": 0, "expired": 0, "missing": 1},
    }


def test_wecom_frontend_csv_upload_rejects_empty_file(monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.post(
        "/api/query/excel",
        files={"file": ("empty.csv", "", "text/csv")},
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "EMPTY_QUERY_FILE"


def test_wecom_frontend_csv_upload_rejects_missing_query_column(monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.post(
        "/api/query/excel",
        files={"file": ("missing-column.csv", "公司名称\n", "text/csv")},
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "MISSING_QUERY_COLUMN"


def test_wecom_frontend_download_manifest_tracks_missing_attachments(tmp_path, monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-no-attachment.pdf",
        supplier_name="无附件测试有限公司",
        supplier_credit_code="91440300NOFILE",
        source_record_id="SRM-NOFILE-001",
        attachment_ref_id="ATT-NOFILE-001",
        source_url="",
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.post(
        "/api/query/download",
        json={"ids": [result.task_id]},
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["records"] == []
    assert manifest["missing_attachment_records"] == [
        {
            "id": result.task_id,
            "company_name": "无附件测试有限公司",
            "reason": "缺少 source_file_url",
        }
    ]


def test_wecom_frontend_records_support_keyword_search_and_export_shape(tmp_path, monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-records-search.pdf",
        supplier_name="广州记录查询有限公司",
        supplier_credit_code="91440100RECORD",
        source_record_id="SRM-RECORD-001",
        attachment_ref_id="ATT-RECORD-001",
        source_url="https://files.example.test/business-records-search.pdf",
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        "/api/records",
        params={"keyword": "广州记录"},
        headers=business_license_auth_headers(client, monkeypatch),
    )
    export_response = client.get(
        "/api/records/export",
        params={"keyword": "广州记录"},
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    record = payload["records"][0]
    assert {"company_name", "license_type", "credit_code", "expire_status", "created_at"}.issubset(record)
    assert export_response.status_code == 200
    assert export_response.headers["content-type"].startswith("text/csv")
    assert "广州记录查询有限公司" in export_response.text


def test_wecom_frontend_dashboard_stats_empty_and_with_data(tmp_path, monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)
    headers = business_license_auth_headers(client, monkeypatch)

    empty_response = client.get("/api/dashboard/stats", headers=headers)
    _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-dashboard.pdf",
        supplier_name="看板统计有限公司",
        supplier_credit_code="91110100DASH001",
        extracted_credit_code="91110100DASH002",
        source_record_id="SRM-DASH-001",
        attachment_ref_id="ATT-DASH-001",
        source_url="https://files.example.test/business-dashboard.pdf",
    )
    data_response = client.get("/api/dashboard/stats", headers=headers)
    daily_response = client.get("/api/dashboard/daily", headers=headers)

    assert empty_response.json()["data"]["total"] == 0
    assert empty_response.json()["data"]["type_distribution"] == []
    assert data_response.json()["data"]["total"] == 1
    assert data_response.json()["data"]["type_distribution"][0]["type"] == "营业执照"
    assert daily_response.json()["data"]["expired"][0]["company_name"] == "看板统计有限公司"


def test_frontend_import_route_and_view_exist():
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[2]
    router_source = (project_root / "web-console/src/router/index.js").read_text()
    import_view = project_root / "web-console/src/views/ImportPage.vue"

    assert "path: '/admin/import'" in router_source
    assert import_view.exists()
    assert "解析预览，不自动入库" in import_view.read_text()


def _repository() -> MySQLReviewResultRepository:
    return business_license_repository()
