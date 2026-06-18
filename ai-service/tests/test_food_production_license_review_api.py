from fastapi.testclient import TestClient

from app.api.qc_reviews import get_food_production_license_srm_sql_client
from app.main import app
from app.tools.remote_document import RemoteDocument
from app.workflows.food_production_license import nodes as food_production_license_nodes
from tests.business_license_helpers import business_license_auth_headers
from tests.mysql_repository_stub import install_mysql_repository_stub
from tests.pdf_helpers import write_minimal_pdf


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


def test_food_production_license_review_from_srm_routes_to_qc_review_boundary(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    _stub_food_production_file_recognition(monkeypatch, tmp_path)

    class StubSrmSqlClient:
        def fetch_all(self, sql):
            return [
                {
                    "uuid": "cert-food-production-001",
                    "refId": "attach-food-production-001",
                    "tenant": "8560",
                    "category": "vendor",
                    "typeName": "食品生产许可证",
                    "vendorName": "成都示例食品生产有限公司",
                    "number": "SC10151010000000",
                    "num": "91510100MA00000000",
                    "url": "https://files.example.test/food-production-license.pdf",
                    "attachmentName": "food-production-license.pdf",
                    "storeId": "oss-key-food-production-license",
                }
            ]

    app.dependency_overrides[get_food_production_license_srm_sql_client] = (
        lambda: StubSrmSqlClient()
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/qc/food-production-license/reviews/from-srm",
        headers=_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["use_case_name"] == "food_production_license"
    assert payload["document_type"] == "food_production_license"
    assert payload["status"] == "REVIEWED"
    assert payload["needs_manual_review"] is False
    assert payload["summary"] == "食品生产许可证规则校验通过"
    assert [rule["rule_code"] for rule in payload["rule_results"]] == [
        "FOOD_PRODUCTION_LICENSE_TYPE_MATCH",
        "FOOD_PRODUCTION_LICENSE_PRODUCER_NAME_MATCH",
        "FOOD_PRODUCTION_LICENSE_CREDIT_CODE_MATCH",
        "FOOD_PRODUCTION_LICENSE_VALIDITY_PERIOD",
    ]
    assert payload["skill_result"]["source_evidence"] == {
        "supplier_name": "成都示例食品生产有限公司",
        "supplier_credit_code": "91510100MA00000000",
        "declared_document_type": "food_production_license",
        "options": {},
        "source": {
            "source_system": "srm",
            "tenant": "8560",
            "record_id": "cert-food-production-001",
            "attachment_ref_id": "attach-food-production-001",
            "document_category": "vendor",
            "document_type_code": None,
            "file_store_key": "oss-key-food-production-license",
            "source_payload": {
                "uuid": "cert-food-production-001",
                "refId": "attach-food-production-001",
                "tenant": "8560",
                "category": "vendor",
                "typeName": "食品生产许可证",
                "vendorName": "成都示例食品生产有限公司",
                "number": "SC10151010000000",
                "num": "91510100MA00000000",
                "url": "https://files.example.test/food-production-license.pdf",
                "attachmentName": "food-production-license.pdf",
                "storeId": "oss-key-food-production-license",
            },
        },
    }


def test_food_production_license_review_from_srm_is_visible_in_qc_review_list(
    tmp_path,
    monkeypatch,
):
    storage = install_mysql_repository_stub(monkeypatch)
    _stub_food_production_file_recognition(monkeypatch, tmp_path)

    class StubSrmSqlClient:
        def fetch_all(self, sql):
            return [
                {
                    "uuid": "cert-food-production-001",
                    "refId": "attach-food-production-001",
                    "tenant": "8560",
                    "category": "vendor",
                    "typeName": "食品生产许可证",
                    "vendorName": "成都示例食品生产有限公司",
                    "number": "SC10151010000000",
                    "num": "91510100MA00000000",
                    "url": "https://files.example.test/food-production-license.pdf",
                    "attachmentName": "food-production-license.pdf",
                    "storeId": "oss-key-food-production-license",
                }
            ]

    app.dependency_overrides[get_food_production_license_srm_sql_client] = (
        lambda: StubSrmSqlClient()
    )

    client = TestClient(app)
    create_response = client.post(
        "/api/v1/qc/food-production-license/reviews/from-srm",
        headers=_auth_headers(client, monkeypatch),
    )
    assert create_response.status_code == 200
    created_task_id = create_response.json()["task_id"]

    list_response = client.get(
        "/api/v1/qc/reviews",
        params={"document_type": "food_production_license"},
        headers=_auth_headers(client, monkeypatch),
    )

    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["task_id"] == created_task_id
    assert payload["items"][0]["document_type"] == "food_production_license"
    assert payload["items"][0]["document_type_label"] == "食品生产许可证"
    assert payload["items"][0]["supplier_name"] == "成都示例食品生产有限公司"
    assert payload["items"][0]["credit_code"] == "91510100MA00000000"
    assert storage["food_production_license_reviews"][created_task_id]["source_record_id"] == (
        "cert-food-production-001"
    )


def test_food_production_license_review_from_srm_returns_not_found(monkeypatch):
    class StubSrmSqlClient:
        def fetch_all(self, sql):
            return []

    app.dependency_overrides[get_food_production_license_srm_sql_client] = (
        lambda: StubSrmSqlClient()
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/qc/food-production-license/reviews/from-srm",
        headers=_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "code": "FOOD_PRODUCTION_LICENSE_SOURCE_RECORD_NOT_FOUND",
        "message": "未找到可审核的食品生产许可证来源记录",
    }


def test_food_production_license_review_from_srm_rejects_missing_url(monkeypatch):
    class StubSrmSqlClient:
        def fetch_all(self, sql):
            return [
                {
                    "uuid": "cert-food-production-001",
                    "typeName": "食品生产许可证",
                    "vendorName": "成都示例食品生产有限公司",
                    "number": "SC10151010000000",
                    "num": "91510100MA00000000",
                }
            ]

    app.dependency_overrides[get_food_production_license_srm_sql_client] = (
        lambda: StubSrmSqlClient()
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/qc/food-production-license/reviews/from-srm",
        headers=_auth_headers(client, monkeypatch),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "FOOD_PRODUCTION_LICENSE_SOURCE_URL_MISSING",
        "message": "食品生产许可证来源记录缺少文件 URL",
        "record_id": "cert-food-production-001",
    }


def _auth_headers(client, monkeypatch):
    return business_license_auth_headers(client, monkeypatch)


def _stub_food_production_file_recognition(monkeypatch, tmp_path):
    pdf_path = tmp_path / "food-production-license.pdf"
    write_minimal_pdf(pdf_path, "食品生产许可证")
    pdf_content = pdf_path.read_bytes()
    monkeypatch.setattr(
        food_production_license_nodes,
        "food_production_license_file_adapter",
        StubFoodProductionFileAdapter(),
    )
    monkeypatch.setattr(
        food_production_license_nodes.food_production_license_remote_downloader,
        "download",
        lambda file_url: RemoteDocument(
            source_url=file_url,
            content=pdf_content,
            file_type="pdf",
            mime_type="application/pdf",
            status_code=200,
            headers={"content-type": "application/pdf"},
        ),
    )


class StubFoodProductionFileAdapter:
    def extract_text(self, source):
        return {
            "text": "",
            "structured_fields": {
                "document_type": "food_production_license",
                "producer_name": "成都示例食品生产有限公司",
                "credit_code": "91510100MA00000000",
                "license_no": "SC10151010000000",
                "food_categories": ["糕点"],
                "valid_to": "2028-06-05",
            },
            "metadata": {
                "implementation_status": "stub",
                "provider": "fake",
                "model": "fake-food-production-license-file-recognition",
            },
        }
