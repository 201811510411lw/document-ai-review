import io
import json
import zipfile
from datetime import date

from fastapi.testclient import TestClient

from app.api.business_license_reviews import get_review_read_repository
from app.main import app
from app.models import ReviewDocumentInput, ReviewInput
from app.repositories.review_result_repository import MySQLReviewResultRepository
from app.services.review_service import ReviewService
from app.workflows.food_license import nodes as food_license_nodes
from app.workflows.food_production_license import nodes as food_production_license_nodes
from tests.business_license_helpers import business_license_auth_headers, business_license_repository
from tests.mysql_repository_stub import install_mysql_repository_stub
from tests.pdf_helpers import write_minimal_pdf
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


def test_wecom_frontend_review_list_filters_business_license_records(tmp_path, monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    business_result = _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-filter.pdf",
        supplier_name="营业执照过滤有限公司",
        supplier_credit_code="91510100FILTER001",
        source_record_id="SRM-BUSINESS-FILTER",
        attachment_ref_id="ATT-BUSINESS-FILTER",
        source_url="https://files.example.test/business-filter.pdf",
    )

    class StubFoodProductionLicenseFileAdapter:
        def extract_text(self, source):
            return {
                "text": "",
                "structured_fields": {
                    "document_type": "food_production_license",
                    "producer_name": "食品生产过滤有限公司",
                    "credit_code": "91510100FILTER002",
                    "license_no": "SC10151010000000",
                    "production_address": "成都市示例区生产路 200 号",
                    "legal_person": "王五",
                    "food_categories": ["糕点"],
                    "valid_to": "2028-06-05",
                },
                "metadata": {"implementation_status": "stub"},
            }

    production_pdf = tmp_path / "food-production-filter.pdf"
    write_minimal_pdf(production_pdf, "embedded text should not be used")
    monkeypatch.setattr(
        food_production_license_nodes,
        "food_production_license_file_adapter",
        StubFoodProductionLicenseFileAdapter(),
    )
    production_result = ReviewService(repository=repository).review(
        ReviewInput(
            file=ReviewDocumentInput(
                local_path=str(production_pdf),
                file_name="food-production-filter.pdf",
                mime_type="application/pdf",
                document_format="pdf",
            ),
            supplier_name="食品生产过滤有限公司",
            supplier_credit_code="91510100FILTER002",
            declared_document_type="food_production_license",
        ),
        use_case_name="food_production_license",
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        "/api/review/list",
        params={"document_type": "business_license"},
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    payload = response.json()
    assert {record["id"] for record in payload["records"]} == {business_result.task_id}
    assert production_result.task_id not in {record["id"] for record in payload["records"]}
    assert payload["stats"]["total"] == 1


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


def test_wecom_frontend_rejects_removed_demo_token(monkeypatch):
    client = TestClient(app)

    profile_response = client.get("/auth/profile", headers={"Authorization": "Bearer demo-token"})
    stats_response = client.get(
        "/api/dashboard/stats",
        headers={"Authorization": "Bearer demo-token"},
    )

    assert profile_response.status_code == 401
    assert stats_response.status_code == 401


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


def test_wecom_frontend_business_license_start_date_falls_back_to_established_date(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-start-date.pdf",
        supplier_name="成都日期兜底有限公司",
        supplier_credit_code="91510100DATE00001X",
        source_record_id="SRM-DATE-001",
        attachment_ref_id="ATT-DATE-001",
        source_url="https://files.example.test/business-start-date.pdf",
    )
    saved = repository.get_by_task_id(result.task_id)
    payload = saved.model_dump(mode="json")
    payload["skill_result"]["extracted_fields"]["valid_from"] = None
    payload["skill_result"]["normalized_fields"]["valid_from"] = None
    payload["skill_result"]["extracted_fields"]["established_date"] = "2023-05-04"
    payload["skill_result"]["normalized_fields"]["established_date"] = "2023-05-04"
    repository.save(saved.__class__.model_validate(payload))
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/review/{result.task_id}",
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    fields = response.json()["record"]["validation_fields"]
    assert [field["field"] for field in fields] == [
        "主体名称",
        "统一社会信用代码",
        "法定代表人",
        "有效期开始",
        "有效期结束",
        "住所",
    ]
    start_date = next(field for field in fields if field["field"] == "有效期开始")
    assert start_date["recognized"] == "2023-05-04"
    assert start_date["expected"] == "2023-05-04"
    assert start_date["match"] is True


def test_wecom_frontend_business_license_subject_name_punctuation_matches(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-subject-punctuation.pdf",
        supplier_name="欧扎克（滁州）食品有限公司",
        supplier_credit_code="91341171MA2WNB2240",
        source_record_id="SRM-SUBJECT-PUNCT",
        attachment_ref_id="ATT-SUBJECT-PUNCT",
        source_url="https://files.example.test/business-subject-punctuation.pdf",
    )
    saved = repository.get_by_task_id(result.task_id)
    payload = saved.model_dump(mode="json")
    payload["skill_result"]["extracted_fields"]["subject_name"] = "欧扎克(滁州)食品有限公司"
    payload["skill_result"]["normalized_fields"]["subject_name"] = "欧扎克滁州食品有限公司"
    repository.save(saved.__class__.model_validate(payload))
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/review/{result.task_id}",
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    fields = response.json()["record"]["validation_fields"]
    subject_name = next(field for field in fields if field["field"] == "主体名称")
    assert subject_name["recognized"] == "欧扎克(滁州)食品有限公司"
    assert subject_name["expected"] == "欧扎克（滁州）食品有限公司"
    assert subject_name["match"] is True


def test_wecom_frontend_business_license_detail_compares_against_source_fields(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-source-mismatch.pdf",
        supplier_name="湖南笑辣辣销售服务有限公司",
        supplier_credit_code="91410328MA467UBROH",
        source_record_id="SRM-SOURCE-MISMATCH",
        attachment_ref_id="ATT-SOURCE-MISMATCH",
        source_url="https://files.example.test/business-source-mismatch.pdf",
    )
    saved = repository.get_by_task_id(result.task_id)
    payload = saved.model_dump(mode="json")
    payload["skill_result"]["extracted_fields"]["subject_name"] = "河南笑笑食品有限公司"
    payload["skill_result"]["normalized_fields"]["subject_name"] = "河南笑笑食品有限公司"
    payload["skill_result"]["extracted_fields"]["credit_code"] = "91410328MA467UBR0H"
    payload["skill_result"]["normalized_fields"]["credit_code"] = "91410328MA467UBR0H"
    repository.save(saved.__class__.model_validate(payload))
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/review/{result.task_id}",
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    fields = response.json()["record"]["validation_fields"]
    subject_name = next(field for field in fields if field["field"] == "主体名称")
    credit_code = next(field for field in fields if field["field"] == "统一社会信用代码")
    assert subject_name["recognized"] == "河南笑笑食品有限公司"
    assert subject_name["expected"] == "湖南笑辣辣销售服务有限公司"
    assert subject_name["match"] is False
    assert credit_code["recognized"] == "91410328MA467UBR0H"
    assert credit_code["expected"] == "91410328MA467UBROH"
    assert credit_code["match"] is False
    assert response.json()["record"]["match_ratio"] == 67


def test_wecom_frontend_business_license_match_ratio_counts_field_matches(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-one-field-mismatch.pdf",
        supplier_name="河南精益珍食品有限公司",
        supplier_credit_code="01",
        source_record_id="SRM-ONE-FIELD-MISMATCH",
        attachment_ref_id="ATT-ONE-FIELD-MISMATCH",
        source_url="https://files.example.test/business-one-field-mismatch.pdf",
    )
    saved = repository.get_by_task_id(result.task_id)
    payload = saved.model_dump(mode="json")
    payload["skill_result"]["extracted_fields"].update(
        {
            "subject_name": "河南精益珍食品有限公司",
            "credit_code": "91410700571016364T",
            "legal_person": "江和兴",
            "established_date": "2011-06-30",
            "valid_to": None,
            "business_address": "延津县产业集聚区管委会园内",
        }
    )
    payload["skill_result"]["normalized_fields"].update(
        {
            "subject_name": "河南精益珍食品有限公司",
            "credit_code": "01",
            "legal_person": "江和兴",
            "established_date": "2011-06-30",
            "valid_to": None,
            "business_address": "延津县产业集聚区管委会园内",
        }
    )
    repository.save(saved.__class__.model_validate(payload))
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/review/{result.task_id}",
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    record = response.json()["record"]
    assert record["match_ratio"] == 83


def test_wecom_frontend_food_license_detail_uses_food_validation_fields(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()

    class StubFoodLicenseFileAdapter:
        def extract_text(self, source):
            return {
                "text": "",
                "structured_fields": {
                    "document_type": "food_license",
                    "subject_name": "成都示例食品有限公司",
                    "credit_code": "91510100MA00000000",
                    "license_no": "JY15101000000000",
                    "business_address": "成都市示例区示例路 100 号",
                    "legal_person": "李四",
                    "business_items": ["预包装食品销售", "散装食品销售"],
                    "valid_to": "2028-06-05",
                },
                "metadata": {"implementation_status": "stub"},
            }

    pdf_path = tmp_path / "food-license-wecom-detail.pdf"
    write_minimal_pdf(pdf_path, "embedded text should not be used")
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_file_adapter",
        StubFoodLicenseFileAdapter(),
    )
    result = ReviewService(repository=repository).review_food_license(
        ReviewInput(
            file=ReviewDocumentInput(
                local_path=str(pdf_path),
                file_name="food-license-wecom-detail.pdf",
                mime_type="application/pdf",
                document_format="pdf",
            ),
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_license",
        )
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/review/{result.task_id}",
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    fields = response.json()["record"]["validation_fields"]
    assert [field["field"] for field in fields] == [
        "经营者名称",
        "统一社会信用代码",
        "许可证编号",
        "经营场所",
        "法定代表人/负责人",
        "经营项目",
        "有效期开始",
        "有效期结束",
        "发证机关",
        "签发日期",
    ]
    business_items = next(field for field in fields if field["field"] == "经营项目")
    assert business_items["recognized"] == "预包装食品销售、散装食品销售"
    assert business_items["match"] is True


def test_wecom_frontend_food_license_subject_name_punctuation_matches(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()

    class StubFoodLicenseFileAdapter:
        def extract_text(self, source):
            return {
                "text": "",
                "structured_fields": {
                    "document_type": "food_license",
                    "subject_name": "好麦多(上海)食品科技有限公司",
                    "credit_code": "91310112MA1GD5WP62",
                    "license_no": "JY13101120198903",
                    "business_address": "上海市闵行区紫星路588号2幢8层17室",
                    "legal_person": "赵孟龙",
                    "business_items": ["食品销售经营者"],
                    "valid_to": "2028-06-05",
                },
                "metadata": {"implementation_status": "stub"},
            }

    pdf_path = tmp_path / "food-license-subject-punctuation.pdf"
    write_minimal_pdf(pdf_path, "embedded text should not be used")
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_file_adapter",
        StubFoodLicenseFileAdapter(),
    )
    result = ReviewService(repository=repository).review_food_license(
        ReviewInput(
            file=ReviewDocumentInput(
                local_path=str(pdf_path),
                file_name="food-license-subject-punctuation.pdf",
                mime_type="application/pdf",
                document_format="pdf",
            ),
            supplier_name="好麦多（上海）食品科技有限公司",
            supplier_credit_code="91310112MA1GD5WP62",
            declared_document_type="food_license",
        )
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/review/{result.task_id}",
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    fields = response.json()["record"]["validation_fields"]
    subject_name = next(field for field in fields if field["field"] == "经营者名称")
    assert subject_name["recognized"] == "好麦多(上海)食品科技有限公司"
    assert subject_name["expected"] == "好麦多（上海）食品科技有限公司"
    assert subject_name["match"] is True


def test_wecom_frontend_food_license_detail_uses_normalized_dates_for_comparison(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()

    class StubFoodLicenseFileAdapter:
        def extract_text(self, source):
            return {
                "text": "",
                "structured_fields": {
                    "document_type": "food_license",
                    "subject_name": "成都示例食品有限公司",
                    "credit_code": "91510100MA00000000",
                    "license_no": "JY15101000000000",
                    "business_address": "成都市示例区示例路 100 号",
                    "legal_person": "李四",
                    "business_items": ["预包装食品销售"],
                    "valid_from": "2023年11月09日",
                    "valid_to": "2028年11月08日",
                },
                "metadata": {"implementation_status": "stub"},
            }

    pdf_path = tmp_path / "food-license-date-format.pdf"
    write_minimal_pdf(pdf_path, "embedded text should not be used")
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_file_adapter",
        StubFoodLicenseFileAdapter(),
    )
    result = ReviewService(repository=repository).review_food_license(
        ReviewInput(
            file=ReviewDocumentInput(
                local_path=str(pdf_path),
                file_name="food-license-date-format.pdf",
                mime_type="application/pdf",
                document_format="pdf",
            ),
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_license",
        )
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/review/{result.task_id}",
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    fields = response.json()["record"]["validation_fields"]
    valid_from = next(field for field in fields if field["field"] == "有效期开始")
    valid_to = next(field for field in fields if field["field"] == "有效期结束")
    assert valid_from["recognized"] == "2023-11-09"
    assert valid_from["expected"] == "2023-11-09"
    assert valid_from["match"] is True
    assert valid_to["recognized"] == "2028-11-08"
    assert valid_to["expected"] == "2028-11-08"
    assert valid_to["match"] is True


def test_wecom_frontend_food_license_expired_valid_to_is_marked_unmatched(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()

    class StubFoodLicenseFileAdapter:
        def extract_text(self, source):
            return {
                "text": "",
                "structured_fields": {
                    "document_type": "food_license",
                    "subject_name": "安徽元气森林销售有限公司",
                    "credit_code": "91341102MA2U2C5A58",
                    "license_no": "JY13411020046050",
                    "business_address": "安徽省滁州市琅琊区琅琊经济开发区雷桥路2号办公楼202室",
                    "legal_person": "张三",
                    "business_items": ["食品销售经营者(批发)"],
                    "valid_from": "2021-03-08",
                    "valid_to": "2026-03-07",
                },
                "metadata": {"implementation_status": "stub"},
            }

    pdf_path = tmp_path / "food-license-expired-valid-to.pdf"
    write_minimal_pdf(pdf_path, "embedded text should not be used")
    monkeypatch.setattr(
        food_license_nodes,
        "_current_rule_date",
        lambda: date(2026, 6, 29),
    )
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_file_adapter",
        StubFoodLicenseFileAdapter(),
    )
    result = ReviewService(repository=repository).review_food_license(
        ReviewInput(
            file=ReviewDocumentInput(
                local_path=str(pdf_path),
                file_name="food-license-expired-valid-to.pdf",
                mime_type="application/pdf",
                document_format="pdf",
            ),
            supplier_name="安徽元气森林销售有限公司",
            supplier_credit_code="91341102MA2U2C5A58",
            declared_document_type="food_license",
        )
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/review/{result.task_id}",
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    record = response.json()["record"]
    valid_to = next(
        field for field in record["validation_fields"] if field["field"] == "有效期结束"
    )
    assert valid_to["recognized"] == "2026-03-07"
    assert valid_to["expected"] == "2026-03-07"
    assert valid_to["match"] is False
    assert valid_to["risk"] == "expired"
    assert record["review_status"] == "pending"


def test_wecom_frontend_food_license_detail_does_not_fallback_credit_code_to_recognized_value(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()

    class StubFoodLicenseFileAdapter:
        def extract_text(self, source):
            return {
                "text": "",
                "structured_fields": {
                    "document_type": "food_license",
                    "subject_name": "东莞市华辉商贸有限公司",
                    "credit_code": "91441900MA54XR353T",
                    "license_no": "JY14419082492249",
                    "business_address": "广东省东莞市寮步镇霞边元下路3号3栋101室",
                    "legal_person": "徐巧君",
                    "business_items": ["食品销售"],
                    "valid_from": "2025-07-15",
                },
                "metadata": {"implementation_status": "stub"},
            }

    pdf_path = tmp_path / "food-license-empty-source-credit-code.pdf"
    write_minimal_pdf(pdf_path, "embedded text should not be used")
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_file_adapter",
        StubFoodLicenseFileAdapter(),
    )
    result = ReviewService(repository=repository).review_food_license(
        ReviewInput(
            file=ReviewDocumentInput(
                local_path=str(pdf_path),
                file_name="food-license-empty-source-credit-code.pdf",
                mime_type="application/pdf",
                document_format="pdf",
            ),
            supplier_name="东莞市华辉商贸有限公司",
            supplier_credit_code="",
            declared_document_type="food_license",
            source={"source_payload": {"num": "1001010427202311270017"}},
        )
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/review/{result.task_id}",
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    record = response.json()["record"]
    credit_code = next(
        field for field in record["validation_fields"] if field["field"] == "统一社会信用代码"
    )
    assert credit_code["recognized"] == "91441900MA54XR353T"
    assert credit_code["expected"] == ""
    assert credit_code["match"] is False
    assert record["match_ratio"] < 100


def test_wecom_frontend_food_license_detail_uses_valid_source_payload_num_as_credit_code(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()

    class StubFoodLicenseFileAdapter:
        def extract_text(self, source):
            return {
                "text": "",
                "structured_fields": {
                    "document_type": "food_license",
                    "subject_name": "上海清硕国际贸易有限公司",
                    "credit_code": "91310116MA1J8TD79M",
                    "license_no": "JY13101160340423",
                    "business_address": "上海市金山区金山卫镇钱鑫路301号4075",
                    "legal_person": "陈伟",
                    "business_items": ["食品销售"],
                    "valid_to": "2026-11-20",
                },
                "metadata": {"implementation_status": "stub"},
            }

    pdf_path = tmp_path / "food-license-source-payload-credit-code.pdf"
    write_minimal_pdf(pdf_path, "embedded text should not be used")
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_file_adapter",
        StubFoodLicenseFileAdapter(),
    )
    result = ReviewService(repository=repository).review_food_license(
        ReviewInput(
            file=ReviewDocumentInput(
                local_path=str(pdf_path),
                file_name="food-license-source-payload-credit-code.pdf",
                mime_type="application/pdf",
                document_format="pdf",
            ),
            supplier_name="上海清硕国际贸易有限公司",
            supplier_credit_code="",
            declared_document_type="food_license",
            source={"source_payload": {"num": "91310116MA1J8TD79M"}},
        )
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/review/{result.task_id}",
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    record = response.json()["record"]
    credit_code = next(
        field for field in record["validation_fields"] if field["field"] == "统一社会信用代码"
    )
    assert credit_code["recognized"] == "91310116MA1J8TD79M"
    assert credit_code["expected"] == "91310116MA1J8TD79M"
    assert credit_code["match"] is True


def test_wecom_frontend_food_production_detail_uses_production_validation_fields(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()

    class StubFoodProductionLicenseFileAdapter:
        def extract_text(self, source):
            return {
                "text": "",
                "structured_fields": {
                    "document_type": "food_production_license",
                    "producer_name": "成都示例食品生产有限公司",
                    "credit_code": "91510100MA00000000",
                    "license_no": "SC10151010000000",
                    "production_address": "成都市示例区生产路 200 号",
                    "legal_person": "王五",
                    "food_categories": ["糕点", "速冻食品"],
                    "valid_to": "2028-06-05",
                },
                "metadata": {"implementation_status": "stub"},
            }

    pdf_path = tmp_path / "food-production-wecom-detail.pdf"
    write_minimal_pdf(pdf_path, "embedded text should not be used")
    monkeypatch.setattr(
        food_production_license_nodes,
        "food_production_license_file_adapter",
        StubFoodProductionLicenseFileAdapter(),
    )
    result = ReviewService(repository=repository).review(
        ReviewInput(
            file=ReviewDocumentInput(
                local_path=str(pdf_path),
                file_name="food-production-wecom-detail.pdf",
                mime_type="application/pdf",
                document_format="pdf",
            ),
            supplier_name="成都示例食品生产有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_production_license",
        ),
        use_case_name="food_production_license",
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/review/{result.task_id}",
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    fields = response.json()["record"]["validation_fields"]
    assert [field["field"] for field in fields] == [
        "生产者名称",
        "统一社会信用代码",
        "许可证编号",
        "生产地址",
        "法定代表人/负责人",
        "食品类别",
        "有效期开始",
        "有效期结束",
        "发证机关",
        "签发日期",
    ]
    food_categories = next(field for field in fields if field["field"] == "食品类别")
    assert food_categories["recognized"] == "糕点、速冻食品"
    assert food_categories["match"] is True


def test_wecom_frontend_product_report_detail_uses_product_report_validation_fields(
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = ReviewService(repository=repository).review(
        ReviewInput(
            ocr_text="""
            产品检验报告
            报告编号：BG-20260610-001
            样品名称：麻辣牛肉
            委托单位：成都示例食品有限公司
            生产商：成都示例食品厂
            批号：20260601-A
            生产日期：2026年06月01日
            签发日期：2026年06月10日
            检验结论：经检验，所检项目符合要求。
            """,
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="",
            declared_document_type="product_report",
        ),
        use_case_name="qc_document_review",
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/review/{result.task_id}",
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    fields = response.json()["record"]["validation_fields"]
    assert [field["field"] for field in fields] == [
        "报告编号",
        "样品名称",
        "委托单位",
        "生产商",
        "批号",
        "生产日期",
        "签发日期",
        "批准日期",
        "有效截止日",
        "检验结论",
    ]
    report_no = next(field for field in fields if field["field"] == "报告编号")
    valid_to = next(field for field in fields if field["field"] == "有效截止日")
    entrusting_party = next(field for field in fields if field["field"] == "委托单位")
    assert report_no["recognized"] == "BG-20260610-001"
    assert valid_to["recognized"] == "2026-12-07"
    assert valid_to["match"] is True
    assert entrusting_party["expected"] == "成都示例食品有限公司"
    assert entrusting_party["match"] is True


def test_wecom_frontend_batch_report_list_detail_and_confirm(monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = ReviewService(repository=repository).review(
        ReviewInput(
            ocr_text="""
            商品批次报告
            厂名：广州市秀雅秀贸易有限公司（常温）
            产品名称：游世佳族金唱片面包
            生产日期：2026年05月08日
            """,
            supplier_name="广州市秀雅秀贸易有限公司（常温）",
            supplier_credit_code="",
            declared_document_type="batch_report",
            source={
                "record_id": "batch-001",
                "order_number": "10102605050385",
                "vendor_name": "广州市秀雅秀贸易有限公司（常温）",
                "sku_name": "游世佳族金唱片面包",
                "production_date": "2026-05-08",
                "attachment_ref_id": "batch-001",
            },
        ),
        use_case_name="qc_document_review",
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)
    headers = business_license_auth_headers(client, monkeypatch)

    list_response = client.get(
        "/api/review/list",
        params={"document_type": "batch_report"},
        headers=headers,
    )
    assert list_response.status_code == 200
    records = list_response.json()["records"]
    assert records[0]["id"] == result.task_id
    assert records[0]["license_type"] == "商品批次报告"
    assert records[0]["product_name"] == "游世佳族金唱片面包"
    assert records[0]["order_number"] == "10102605050385"

    detail_response = client.get(f"/api/review/{result.task_id}", headers=headers)
    assert detail_response.status_code == 200
    record = detail_response.json()["record"]
    assert record["document_type"] == "batch_report"
    fields = record["validation_fields"]
    assert [field["field"] for field in fields] == [
        "文档类型",
        "商品名称",
        "生产者名称",
        "生产日期",
        "生产批号",
        "文档文本",
        "生产日期/批号",
    ]
    product_name = next(field for field in fields if field["field"] == "商品名称")
    assert product_name["expected"] == "游世佳族金唱片面包"
    assert product_name["match"] is True

    confirm_response = client.post(
        f"/api/review/{result.task_id}/confirm",
        json={"comment": "已确认批次报告。"},
        headers=headers,
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["record"]["review_status"] == "confirmed"


def test_wecom_frontend_food_production_detail_prefers_payload_document_type_over_stale_projection(
    tmp_path,
    monkeypatch,
):
    storage = install_mysql_repository_stub(monkeypatch)
    repository = _repository()

    class StubFoodProductionLicenseFileAdapter:
        def extract_text(self, source):
            return {
                "text": "",
                "structured_fields": {
                    "document_type": "food_production_license",
                    "producer_name": "河南晚柔食品科技有限公司",
                    "credit_code": "91450203MA5MTFWN72",
                    "license_no": "SC10344040400307",
                    "food_categories": ["调味品"],
                    "valid_to": "2027-12-19",
                },
                "metadata": {"implementation_status": "stub"},
            }

    pdf_path = tmp_path / "food-production-stale-projection.pdf"
    write_minimal_pdf(pdf_path, "embedded text should not be used")
    monkeypatch.setattr(
        food_production_license_nodes,
        "food_production_license_file_adapter",
        StubFoodProductionLicenseFileAdapter(),
    )
    result = ReviewService(repository=repository).review(
        ReviewInput(
            file=ReviewDocumentInput(
                local_path=str(pdf_path),
                file_name="food-production-stale-projection.pdf",
                mime_type="application/pdf",
                document_format="pdf",
            ),
            supplier_name="河南晚柔食品科技有限公司",
            supplier_credit_code="",
            declared_document_type="food_production_license",
        ),
        use_case_name="food_production_license",
    )
    food_projection = storage["food_production_license_reviews"][result.task_id]
    storage["business_license_reviews"][result.task_id] = {
        **food_projection,
        "document_type": "business_license",
        "business_name": None,
        "business_address": None,
        "legal_person": None,
        "valid_from": None,
        "valid_to": None,
        "issue_authority": None,
        "issue_date": None,
    }
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/review/{result.task_id}",
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    record = response.json()["record"]
    assert record["document_type"] == "food_production_license"
    assert record["license_type"] == "食品生产许可证"
    assert [field["field"] for field in record["validation_fields"]] == [
        "生产者名称",
        "统一社会信用代码",
        "许可证编号",
        "生产地址",
        "法定代表人/负责人",
        "食品类别",
        "有效期开始",
        "有效期结束",
        "发证机关",
        "签发日期",
    ]


def test_wecom_frontend_food_production_required_empty_fields_are_mismatches(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()

    class StubFoodProductionLicenseFileAdapter:
        def extract_text(self, source):
            return {
                "text": "",
                "structured_fields": {
                    "document_type": "food_production_license",
                    "producer_name": "珠海佳霖食品有限公司",
                    "credit_code": None,
                    "license_no": "SC10344040400307",
                    "production_address": None,
                    "legal_person": None,
                    "food_categories": ["淀粉及淀粉制品", "调味品"],
                    "valid_from": None,
                    "valid_to": None,
                    "issue_authority": None,
                    "issue_date": None,
                },
                "metadata": {"implementation_status": "stub"},
            }

    pdf_path = tmp_path / "food-production-required-empty.pdf"
    write_minimal_pdf(pdf_path, "embedded text should not be used")
    monkeypatch.setattr(
        food_production_license_nodes,
        "food_production_license_file_adapter",
        StubFoodProductionLicenseFileAdapter(),
    )
    result = ReviewService(repository=repository).review(
        ReviewInput(
            file=ReviewDocumentInput(
                local_path=str(pdf_path),
                file_name="food-production-required-empty.pdf",
                mime_type="application/pdf",
                document_format="pdf",
            ),
            supplier_name="珠海佳霖食品有限公司",
            supplier_credit_code="",
            declared_document_type="food_production_license",
        ),
        use_case_name="food_production_license",
    )
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/review/{result.task_id}",
        headers=business_license_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    record = response.json()["record"]
    fields = record["validation_fields"]
    credit_code = next(field for field in fields if field["field"] == "统一社会信用代码")
    production_address = next(field for field in fields if field["field"] == "生产地址")
    valid_to = next(field for field in fields if field["field"] == "有效期结束")
    assert record["match_ratio"] < 100
    assert credit_code["required"] is True
    assert credit_code["missing_recognized"] is True
    assert credit_code["missing_expected"] is True
    assert credit_code["match"] is False
    assert production_address["missing_recognized"] is True
    assert production_address["match"] is False
    assert valid_to["missing_recognized"] is True
    assert valid_to["match"] is False


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
