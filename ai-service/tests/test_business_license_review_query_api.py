from datetime import datetime

from fastapi.testclient import TestClient

from app.api.business_license_reviews import get_review_read_repository
from app.main import app
from app.models import ReviewDocumentInput, ReviewInput
from app.services.review_service import ReviewService
from app.repositories.review_result_repository import MySQLReviewResultRepository
from tests.business_license_helpers import (
    business_license_auth_headers,
    business_license_repository,
)
from tests.mysql_repository_stub import install_mysql_repository_stub
from tests.pdf_helpers import write_minimal_pdf


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


def test_business_license_review_list_supports_filters_pagination_and_metrics(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-1.pdf",
        supplier_name="成都示例商贸有限公司",
        supplier_credit_code="91510100MA0000000X",
        source_record_id="SRM-CERT-001",
        attachment_ref_id="ATT-001",
        source_url="https://files.example.test/business-1.pdf",
    )
    _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-2.pdf",
        supplier_name="上海云岚供应链管理有限公司",
        supplier_credit_code="91310115MA1K00002Q",
        extracted_credit_code="91310115MA1K00002R",
        source_record_id="SRM-CERT-002",
        attachment_ref_id="ATT-002",
        source_url="https://files.example.test/business-2.pdf",
    )

    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        "/api/v1/business-license/reviews",
        params={
            "risk_level": "HIGH",
            "review_status": "PENDING_MANUAL_REVIEW",
            "page": 1,
            "page_size": 10,
        },
        headers=_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["page"] == 1
    assert payload["page_size"] == 10
    assert payload["total_pages"] == 1
    assert payload["metrics"] == {
        "today_reviewed": 1,
        "pending_manual_review": 1,
        "high_risk": 1,
        "pass_rate": 0,
    }
    row = payload["items"][0]
    assert row["business_name"] == "上海云岚供应链管理有限公司"
    assert row["credit_code"] == "91310115MA1K00002R"
    assert row["review_status"] == "PENDING_MANUAL_REVIEW"
    assert row["review_status_label"] == "待人工复核"
    assert row["risk_level"] == "HIGH"
    assert row["risk_level_label"] == "高风险"
    assert row["needs_manual_review"] is True
    assert row["source_record_id"] == "SRM-CERT-002"


def test_business_license_review_list_date_filter_covers_local_business_day(
    tmp_path,
    monkeypatch,
):
    storage = install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    before_today = _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-before.pdf",
        supplier_name="成都昨日商贸有限公司",
        supplier_credit_code="91510100MA0000000Y",
        source_record_id="SRM-CERT-BEFORE",
        attachment_ref_id="ATT-BEFORE",
        source_url="https://files.example.test/business-before.pdf",
    )
    start_today = _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-start.pdf",
        supplier_name="成都今日早间商贸有限公司",
        supplier_credit_code="91510100MA0000000S",
        source_record_id="SRM-CERT-START",
        attachment_ref_id="ATT-START",
        source_url="https://files.example.test/business-start.pdf",
    )
    end_today = _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-end.pdf",
        supplier_name="成都今日晚间商贸有限公司",
        supplier_credit_code="91510100MA0000000E",
        source_record_id="SRM-CERT-END",
        attachment_ref_id="ATT-END",
        source_url="https://files.example.test/business-end.pdf",
    )
    after_today = _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-after.pdf",
        supplier_name="成都明日商贸有限公司",
        supplier_credit_code="91510100MA0000000A",
        source_record_id="SRM-CERT-AFTER",
        attachment_ref_id="ATT-AFTER",
        source_url="https://files.example.test/business-after.pdf",
    )
    storage["business_license_reviews"][before_today.task_id]["created_at"] = (
        "2026-06-14T23:59:59+08:00"
    )
    storage["business_license_reviews"][start_today.task_id]["created_at"] = (
        "2026-06-15T00:00:00+08:00"
    )
    storage["business_license_reviews"][end_today.task_id]["created_at"] = (
        "2026-06-15T23:59:59+08:00"
    )
    storage["business_license_reviews"][after_today.task_id]["created_at"] = (
        "2026-06-16T00:00:00+08:00"
    )

    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        "/api/v1/business-license/reviews",
        params={
            "created_from": "2026-06-15",
            "created_to": "2026-06-15",
            "page": 1,
            "page_size": 10,
        },
        headers=_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert {item["source_record_id"] for item in payload["items"]} == {
        "SRM-CERT-START",
        "SRM-CERT-END",
    }


def test_business_license_review_detail_returns_projection_and_full_payload(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-detail.pdf",
        supplier_name="上海云岚供应链管理有限公司",
        supplier_credit_code="91310115MA1K00002Q",
        extracted_credit_code="91310115MA1K00002R",
        source_record_id="SRM-CERT-002",
        attachment_ref_id="ATT-002",
        source_url="https://files.example.test/business-detail.pdf",
    )

    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        f"/api/v1/business-license/reviews/{result.task_id}",
        headers=_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == result.task_id
    assert payload["business_name"] == "上海云岚供应链管理有限公司"
    assert payload["source_record_id"] == "SRM-CERT-002"
    assert payload["source_attachment_ref_id"] == "ATT-002"
    assert payload["source_url"] == "https://files.example.test/business-detail.pdf"
    assert payload["review_status"] == "PENDING_MANUAL_REVIEW"
    assert payload["manual_review_reasons"] == ["证照统一社会信用代码与供应商信用代码不一致。"]
    assert payload["extracted_fields"]["credit_code"] == "91310115MA1K00002R"
    assert payload["rule_results"][0]["rule_code"] == "BUSINESS_LICENSE_TYPE_MATCH"
    assert payload["payload"]["task_id"] == result.task_id


def test_business_license_review_persistence_accepts_srm_datetime_source_payload(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-srm-datetime.pdf",
        supplier_name="重庆示例科技有限公司",
        supplier_credit_code="91500000MA00000000",
        source_record_id="SRM-CERT-DATETIME",
        attachment_ref_id="ATT-DATETIME",
        source_url="https://files.example.test/business-srm-datetime.pdf",
        extra_source={
            "source_payload": {
                "created": datetime(2026, 4, 10, 10, 15, 31),
                "expiredEnd": datetime(2099, 12, 31, 23, 59, 59),
            }
        },
    )

    snapshot = repository.get_business_license_snapshot(result.task_id)

    assert snapshot is not None
    source_payload = snapshot["source_evidence"]["source"]["source_payload"]
    assert source_payload["created"] == "2026-04-10T10:15:31"
    assert source_payload["expiredEnd"] == "2099-12-31T23:59:59"


def test_business_license_manual_review_writes_decision_and_audit_event(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-manual.pdf",
        supplier_name="上海云岚供应链管理有限公司",
        supplier_credit_code="91310115MA1K00002Q",
        extracted_credit_code="91310115MA1K00002R",
        source_record_id="SRM-CERT-002",
        attachment_ref_id="ATT-002",
        source_url="https://files.example.test/business-manual.pdf",
    )

    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.post(
        f"/api/v1/business-license/reviews/{result.task_id}/manual-review",
        json={
            "decision": "approved",
            "comment": "已核对原始营业执照，主体和信用代码可接受。",
            "reviewer_id": "wecom-reviewer-001",
        },
        headers=_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["review_status"] == "MANUAL_REVIEWED"
    assert payload["review_status_label"] == "人工已复核"
    assert payload["needs_manual_review"] is False
    assert payload["manual_review"]["status"] == "COMPLETED"
    assert payload["manual_review"]["decision"] == "approved"
    assert payload["manual_review"]["comment"] == "已核对原始营业执照，主体和信用代码可接受。"
    assert payload["manual_review"]["reviewer_id"] == "wecom-reviewer-001"
    assert payload["manual_review"]["reviewer_username"] == "reviewer"
    assert payload["reviewer_id"] == "wecom-reviewer-001"
    assert payload["reviewer_username"] == "reviewer"
    assert payload["manual_review_decision"] == "approved"
    assert payload["manual_review_comment"] == "已核对原始营业执照，主体和信用代码可接受。"
    assert payload["reviewed_at"] is not None
    assert payload["payload"]["status"] == "MANUAL_REVIEWED"
    assert payload["payload"]["needs_manual_review"] is False
    assert payload["payload"]["manual_review"]["status"] == "COMPLETED"
    manual_review_event = next(
        event
        for event in payload["audit_events"]
        if event["event_type"] == "BUSINESS_LICENSE_MANUAL_REVIEW"
    )
    assert manual_review_event["details"]["decision"] == "approved"

    detail_response = client.get(
        f"/api/v1/business-license/reviews/{result.task_id}",
        headers=_auth_headers(client, monkeypatch),
    )

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["review_status"] == "MANUAL_REVIEWED"
    assert detail_payload["needs_manual_review"] is False
    assert detail_payload["manual_review"]["decision"] == "approved"
    assert detail_payload["reviewer_id"] == "wecom-reviewer-001"
    assert detail_payload["reviewer_username"] == "reviewer"
    assert detail_payload["manual_review_decision"] == "approved"
    assert detail_payload["manual_review_comment"] == "已核对原始营业执照，主体和信用代码可接受。"
    assert detail_payload["reviewed_at"] is not None
    detail_manual_review_event = next(
        event
        for event in detail_payload["audit_events"]
        if event["event_type"] == "BUSINESS_LICENSE_MANUAL_REVIEW"
    )
    assert detail_manual_review_event["details"]["reviewer_id"] == "wecom-reviewer-001"
    assert detail_payload["payload"]["status"] == "MANUAL_REVIEWED"
    assert detail_payload["payload"]["needs_manual_review"] is False
    assert detail_payload["payload"]["manual_review"]["status"] == "COMPLETED"
    assert detail_payload["payload"]["manual_review"]["action"] == "approved"
    assert detail_payload["payload"]["manual_review"]["comment"] == "已核对原始营业执照，主体和信用代码可接受。"
    assert detail_payload["payload"]["manual_review"]["reviewer"] == "wecom-reviewer-001"
    assert detail_payload["payload"]["audit_events"][-1]["event_type"] == "BUSINESS_LICENSE_MANUAL_REVIEW"


def test_business_license_manual_review_requires_login(monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.post(
        "/api/v1/business-license/reviews/review-task-1/manual-review",
        json={
            "decision": "approved",
            "comment": "已核对。",
            "reviewer_id": "wecom-reviewer-001",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == {
        "code": "UNAUTHORIZED",
        "message": "请先登录工作台",
    }


def test_business_license_manual_review_returns_404_for_missing_task(monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.post(
        "/api/v1/business-license/reviews/missing-task/manual-review",
        json={
            "decision": "rejected",
            "comment": "无法确认原始证照真实性。",
            "reviewer_id": "wecom-reviewer-001",
        },
        headers=_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "code": "BUSINESS_LICENSE_REVIEW_NOT_FOUND",
        "message": "未找到营业执照审核结果",
    }


def test_business_license_manual_review_rejects_unknown_decision(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-invalid-decision.pdf",
        supplier_name="上海云岚供应链管理有限公司",
        supplier_credit_code="91310115MA1K00002Q",
        extracted_credit_code="91310115MA1K00002R",
        source_record_id="SRM-CERT-002",
        attachment_ref_id="ATT-002",
        source_url="https://files.example.test/business-invalid-decision.pdf",
    )

    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.post(
        f"/api/v1/business-license/reviews/{result.task_id}/manual-review",
        json={
            "decision": "pending",
            "comment": "非法结论。",
            "reviewer_id": "wecom-reviewer-001",
        },
        headers=_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 422


def test_business_license_manual_review_rejects_blank_comment(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = _save_review(
        tmp_path,
        monkeypatch,
        repository,
        task_name="business-blank-comment.pdf",
        supplier_name="上海云岚供应链管理有限公司",
        supplier_credit_code="91310115MA1K00002Q",
        extracted_credit_code="91310115MA1K00002R",
        source_record_id="SRM-CERT-002",
        attachment_ref_id="ATT-002",
        source_url="https://files.example.test/business-blank-comment.pdf",
    )

    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.post(
        f"/api/v1/business-license/reviews/{result.task_id}/manual-review",
        json={
            "decision": "approved",
            "comment": "   ",
            "reviewer_id": "wecom-reviewer-001",
        },
        headers=_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 422


def test_business_license_review_detail_returns_404(monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()

    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get(
        "/api/v1/business-license/reviews/missing-task",
        headers=_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "code": "BUSINESS_LICENSE_REVIEW_NOT_FOUND",
        "message": "未找到营业执照审核结果",
    }


def test_business_license_review_list_requires_login(monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    app.dependency_overrides[get_review_read_repository] = lambda: repository
    client = TestClient(app)

    response = client.get("/api/v1/business-license/reviews")

    assert response.status_code == 401
    assert response.json()["detail"] == {
        "code": "UNAUTHORIZED",
        "message": "请先登录工作台",
    }


def _save_review(
    tmp_path,
    monkeypatch,
    repository,
    *,
    task_name: str,
    supplier_name: str,
    supplier_credit_code: str,
    source_record_id: str,
    attachment_ref_id: str,
    source_url: str,
    extracted_credit_code: str | None = None,
    extra_source: dict | None = None,
):
    pdf_path = tmp_path / task_name
    write_minimal_pdf(pdf_path, "embedded text should not be used")
    monkeypatch.setenv(
        "BUSINESS_LICENSE_FAKE_VISION_JSON",
        f"""
        {{
          "document_type": "business_license",
          "subject_name": "{supplier_name}",
          "credit_code": "{extracted_credit_code or supplier_credit_code}",
          "business_address": "成都市高新区天府大道 1 号",
          "legal_person": "张三",
          "valid_from": "2020-01-02",
          "valid_to": "2030-01-01"
        }}
        """,
    )
    monkeypatch.delenv("BUSINESS_LICENSE_FAKE_VISION_TEXT", raising=False)

    return ReviewService(repository=repository).review(
        ReviewInput(
            file=ReviewDocumentInput(
                local_path=str(pdf_path),
                file_name=task_name,
                mime_type="application/pdf",
                document_format="pdf",
                file_uri=source_url,
            ),
            supplier_name=supplier_name,
            supplier_credit_code=supplier_credit_code,
            declared_document_type="business_license",
            source={
                "tenant": "8560",
                "record_id": source_record_id,
                "attachment_ref_id": attachment_ref_id,
                **(extra_source or {}),
            },
        ),
        use_case_name="business_license",
    )


def _repository() -> MySQLReviewResultRepository:
    return business_license_repository()


def _auth_headers(client: TestClient, monkeypatch) -> dict[str, str]:
    return business_license_auth_headers(client, monkeypatch)
