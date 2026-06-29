from datetime import datetime

from fastapi.testclient import TestClient
from uuid import UUID

from app.api.food_license_reviews import get_review_service, get_srm_sql_client
from app.main import app
from app.models import ReviewResult
from app.workflows.food_license import nodes as food_license_nodes
from app.workflows.food_production_license import nodes as food_production_license_nodes
from tests.business_license_helpers import business_license_auth_headers
from tests.mysql_repository_stub import install_mysql_repository_stub
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
    install_mysql_repository_stub(monkeypatch)
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


def test_food_license_review_from_srm_runs_review_with_source_evidence(monkeypatch):
    monkeypatch.setenv("DOCUMENT_AI_REVIEW_DEBUG", "true")
    install_mysql_repository_stub(monkeypatch)

    class StubSrmSqlClient:
        def fetch_all(self, sql):
            return [
                {
                    "uuid": "cert-food-001",
                    "refId": "attach-food-001",
                    "tenant": "8560",
                    "category": "vendor",
                    "typeName": "食品经营许可证",
                    "vendorName": "成都示例食品有限公司",
                    "number": "JY15101000000000",
                    "num": "91510100MA00000000",
                    "url": "https://files.example.test/food-license.png",
                    "attachmentName": "food-license.png",
                    "storeId": "oss-key-food-license",
                }
            ]

    class StubFileAdapter:
        def extract_text(self, source):
            return {
                "text": "",
                "structured_fields": {
                    "document_type": "food_license",
                    "subject_name": "成都示例食品有限公司",
                    "credit_code": "91510100MA00000000",
                    "license_no": "JY15101000000000",
                    "business_items": ["预包装食品销售"],
                    "valid_to": "2028-06-05",
                },
                "metadata": {"implementation_status": "fake"},
            }

    class StubDownloader:
        def download(self, file_url):
            from app.tools.remote_document import RemoteDocument

            return RemoteDocument(
                source_url=file_url,
                content=b"fake-remote-png",
                file_type="png",
                mime_type="image/png",
                status_code=200,
                headers={"content-type": "image/png"},
            )

    app.dependency_overrides[get_srm_sql_client] = lambda: StubSrmSqlClient()
    monkeypatch.setattr(food_license_nodes, "food_license_file_adapter", StubFileAdapter())
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_remote_downloader",
        StubDownloader(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/food-license/reviews/from-srm",
        headers=_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["use_case_name"] == "food_license"
    assert payload["document_type"] == "food_license"
    assert payload["status"] == "REVIEWED"
    assert payload["needs_manual_review"] is False
    source = payload["skill_result"]["source_evidence"]["source"]
    assert source["record_id"] == "cert-food-001"
    assert source["attachment_ref_id"] == "attach-food-001"
    assert source["file_store_key"] == "oss-key-food-license"
    assert source["source_payload"]["typeName"] == "食品经营许可证"


def test_food_license_review_from_srm_routes_food_production_evidence_to_production_workflow(
    monkeypatch,
):
    monkeypatch.setenv("DOCUMENT_AI_REVIEW_DEBUG", "true")
    install_mysql_repository_stub(monkeypatch)

    class StubSrmSqlClient:
        def fetch_all(self, sql):
            return [
                {
                    "uuid": "2b2d05d6-d63f-4630-bd85-bbaacfc704fd",
                    "refId": "attach-food-production-001",
                    "tenant": "8560",
                    "category": "vendor",
                    "typeName": "食品经营许可证",
                    "remark": "食品生产许可证",
                    "vendorName": "江苏香之派食品有限公司",
                    "number": "781923075088699392",
                    "num": "SC10432130000012",
                    "url": "https://files.example.test/食品生产许可证.jpg",
                    "attachmentName": "食品生产许可证.jpg",
                    "storeId": "vss-web/8560/certification/食品生产许可证.jpg",
                }
            ]

    class StubFoodProductionFileAdapter:
        def extract_text(self, source):
            return {
                "text": "",
                "structured_fields": {
                    "document_type": "food_production_license",
                    "producer_name": "江苏香之派食品有限公司",
                    "credit_code": "91321323314091953H",
                    "license_no": "SC10432130000012",
                    "legal_person": "王波",
                    "food_categories": ["肉制品"],
                    "valid_from": "2023-06-07",
                    "valid_to": "2028-04-09",
                },
                "metadata": {"implementation_status": "fake"},
            }

    class StubDownloader:
        def download(self, file_url):
            from app.tools.remote_document import RemoteDocument

            return RemoteDocument(
                source_url=file_url,
                content=b"fake-production-license-image",
                file_type="jpg",
                mime_type="image/jpeg",
                status_code=200,
                headers={"content-type": "image/jpeg"},
            )

    app.dependency_overrides[get_srm_sql_client] = lambda: StubSrmSqlClient()
    monkeypatch.setattr(
        food_production_license_nodes,
        "food_production_license_file_adapter",
        StubFoodProductionFileAdapter(),
    )
    monkeypatch.setattr(
        food_production_license_nodes,
        "food_production_license_remote_downloader",
        StubDownloader(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/food-license/reviews/from-srm",
        headers=_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "review-task-2b2d05d6-d63f-4630-bd85-bbaacfc704fd"
    assert payload["use_case_name"] == "food_production_license"
    assert payload["document_type"] == "food_production_license"
    source = payload["skill_result"]["source_evidence"]["source"]
    assert source["source_payload"]["typeName"] == "食品经营许可证"
    assert source["document_type_evidence"] == {
        "declared_document_type": "food_license",
        "resolved_document_type": "food_production_license",
        "hints": [
            "remark:食品生产许可证",
            "attachmentName:食品生产许可证",
            "storeId:食品生产许可证",
            "url:食品生产许可证",
            "num:SC",
        ],
        "conflict": True,
    }
    assert payload["skill_result"]["extracted_fields"]["license_no"] == "SC10432130000012"


def test_food_license_review_from_srm_routes_food_production_detail_attachment_to_production_workflow(
    monkeypatch,
):
    monkeypatch.setenv("DOCUMENT_AI_REVIEW_DEBUG", "true")
    install_mysql_repository_stub(monkeypatch)

    class StubSrmSqlClient:
        def fetch_all(self, sql):
            return [
                {
                    "uuid": "97f1c862-0b02-4bc5-b452-4482fcdd2357",
                    "refId": "attach-food-production-detail",
                    "tenant": "8560",
                    "category": "vendor",
                    "typeName": "食品经营许可证",
                    "vendorName": "浙江优拉食品有限公司",
                    "number": "SC10833040205187",
                    "url": "https://files.example.test/2-3食品生产许可品种明细表.jpg",
                    "attachmentName": "2-3食品生产许可品种明细表.jpg",
                }
            ]

    class StubFoodProductionFileAdapter:
        def extract_text(self, source):
            return {
                "text": "",
                "structured_fields": {
                    "document_type": "food_production_license",
                    "producer_name": "浙江优拉食品有限公司",
                    "license_no": "SC10833040205187",
                    "food_categories": ["饼干", "膨化食品"],
                    "valid_to": "2027-09-04",
                    "issue_date": "2024-01-02",
                },
                "metadata": {"implementation_status": "fake"},
            }

    class StubDownloader:
        def download(self, file_url):
            from app.tools.remote_document import RemoteDocument

            return RemoteDocument(
                source_url=file_url,
                content=b"fake-production-license-detail-image",
                file_type="jpg",
                mime_type="image/jpeg",
                status_code=200,
                headers={"content-type": "image/jpeg"},
            )

    app.dependency_overrides[get_srm_sql_client] = lambda: StubSrmSqlClient()
    monkeypatch.setattr(
        food_production_license_nodes,
        "food_production_license_file_adapter",
        StubFoodProductionFileAdapter(),
    )
    monkeypatch.setattr(
        food_production_license_nodes,
        "food_production_license_remote_downloader",
        StubDownloader(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/food-license/reviews/from-srm",
        headers=_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "review-task-97f1c862-0b02-4bc5-b452-4482fcdd2357"
    assert payload["use_case_name"] == "food_production_license"
    assert payload["document_type"] == "food_production_license"
    source = payload["skill_result"]["source_evidence"]["source"]
    assert source["document_type_evidence"] == {
        "declared_document_type": "food_license",
        "resolved_document_type": "food_production_license",
        "hints": [
            "attachmentName:食品生产许可品种明细表",
            "url:食品生产许可品种明细表",
            "number:SC",
        ],
        "conflict": True,
    }
    assert payload["skill_result"]["extracted_fields"]["license_no"] == "SC10833040205187"


def test_food_license_review_from_srm_returns_not_found(monkeypatch):
    class StubSrmSqlClient:
        def fetch_all(self, sql):
            return []

    app.dependency_overrides[get_srm_sql_client] = lambda: StubSrmSqlClient()

    client = TestClient(app)
    response = client.post(
        "/api/v1/food-license/reviews/from-srm",
        headers=_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "code": "FOOD_LICENSE_SOURCE_RECORD_NOT_FOUND",
        "message": "未找到可审核的食品经营许可证来源记录",
    }


def test_food_license_review_from_srm_rejects_missing_url(monkeypatch):
    class StubSrmSqlClient:
        def fetch_all(self, sql):
            return [
                {
                    "uuid": "cert-food-001",
                    "typeName": "食品经营许可证",
                    "vendorName": "成都示例食品有限公司",
                    "number": "JY15101000000000",
                    "num": "91510100MA00000000",
                }
            ]

    app.dependency_overrides[get_srm_sql_client] = lambda: StubSrmSqlClient()

    client = TestClient(app)
    response = client.post(
        "/api/v1/food-license/reviews/from-srm",
        headers=_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "FOOD_LICENSE_SOURCE_URL_MISSING",
        "message": "食品经营许可证来源记录缺少文件 URL",
        "record_id": "cert-food-001",
    }


def test_food_license_review_from_srm_compacts_response_when_debug_disabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DOCUMENT_AI_REVIEW_DEBUG", "false")
    response = _create_food_license_review_from_srm(tmp_path, monkeypatch)

    assert response.status_code == 200
    payload = response.json()
    assert "audit_events" not in payload
    assert set(payload["skill_result"]) == {"extracted_fields"}
    assert "source_evidence" not in payload["skill_result"]


def test_food_license_review_from_srm_keeps_full_response_when_debug_enabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DOCUMENT_AI_REVIEW_DEBUG", "true")
    response = _create_food_license_review_from_srm(tmp_path, monkeypatch)

    assert response.status_code == 200
    payload = response.json()
    source = payload["skill_result"]["source_evidence"]["source"]
    assert source["source_payload"]["typeName"] == "食品经营许可证"


def _create_food_license_review_from_srm(tmp_path, monkeypatch):
    class StubSrmSqlClient:
        def fetch_all(self, sql):
            return [
                {
                    "uuid": "cert-food-001",
                    "refId": "attach-food-001",
                    "tenant": "8560",
                    "category": "vendor",
                    "typeName": "食品经营许可证",
                    "vendorName": "成都示例食品有限公司",
                    "number": "JY15101000000000",
                    "num": "91510100MA00000000",
                    "url": "https://files.example.test/food-license.png",
                    "attachmentName": "food-license.png",
                    "storeId": "oss-key-food-license",
                }
            ]

    class StubFileAdapter:
        def extract_text(self, source):
            return {
                "text": "",
                "structured_fields": {
                    "document_type": "food_license",
                    "subject_name": "成都示例食品有限公司",
                    "credit_code": "91510100MA00000000",
                    "license_no": "JY15101000000000",
                    "business_items": ["预包装食品销售"],
                    "valid_to": "2028-06-05",
                },
                "metadata": {"implementation_status": "fake"},
            }

    class StubDownloader:
        def download(self, file_url):
            from app.tools.remote_document import RemoteDocument

            return RemoteDocument(
                source_url=file_url,
                content=b"fake-remote-png",
                file_type="png",
                mime_type="image/png",
                status_code=200,
                headers={"content-type": "image/png"},
            )

    app.dependency_overrides[get_srm_sql_client] = lambda: StubSrmSqlClient()
    monkeypatch.setattr(food_license_nodes, "food_license_file_adapter", StubFileAdapter())
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_remote_downloader",
        StubDownloader(),
    )

    client = TestClient(app)
    return client.post(
        "/api/v1/food-license/reviews/from-srm",
        headers=_auth_headers(client, monkeypatch),
    )


def _is_review_task_uuid(task_id: str) -> bool:
    prefix = "review-task-"
    if not task_id.startswith(prefix):
        return False
    try:
        UUID(task_id.removeprefix(prefix))
    except ValueError:
        return False
    return True


def _auth_headers(client, monkeypatch):
    return business_license_auth_headers(client, monkeypatch)
