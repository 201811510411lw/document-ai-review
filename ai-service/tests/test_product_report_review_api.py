from fastapi.testclient import TestClient

from app.api.qc_reviews import (
    get_product_report_srm_sql_client,
    get_review_service,
)
from app.main import app
from app.models import ReviewResult
from app.services.review_service import ReviewService
from tests.business_license_helpers import business_license_auth_headers


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


def test_product_report_review_from_srm_routes_to_qc_document_review():
    calls = []

    class StubSrmSqlClient:
        def fetch_all(self, sql):
            return [
                {
                    "uuid": "cert-product-report-001",
                    "refId": "cert-product-report-001",
                    "attachment_uuid": "attach-product-report-001",
                    "tenant": "8560",
                    "category": "sku",
                    "typeName": "产品报告",
                    "vendorId": "VENDOR-001",
                    "vendorName": "广东乃一口食品有限公司",
                    "number": "797120694064660482",
                    "num": "1001010562202606290001",
                    "url": "https://files.example.test/product-report.pdf",
                    "attachmentName": "鲜切蛋糕(蓝莓风味)_广东乃一口食品有限公司_TS10970001.pdf",
                    "storeId": "oss-key-product-report",
                    "deleted": 0,
                    "removed": 0,
                }
            ]

    class StubReviewService(ReviewService):
        def review(self, review_input, *, use_case_name=None) -> ReviewResult:
            calls.append((review_input, use_case_name))
            return super().review(
                review_input.model_copy(
                    update={
                        "ocr_text": """
                        检验报告
                        报告编号：A2260511467101001C
                        样品名称：鲜切蛋糕(蓝莓风味)
                        委托单位：广东乃一口食品有限公司
                        签发日期：2026年06月29日
                        检验结论：所检项目符合相关食品安全标准要求
                        """
                    }
                ),
                use_case_name=use_case_name,
            )

    app.dependency_overrides[get_product_report_srm_sql_client] = lambda: StubSrmSqlClient()
    app.dependency_overrides[get_review_service] = lambda: StubReviewService()

    client = TestClient(app)
    response = client.post(
        "/api/v1/qc/product-report/reviews/from-srm",
        headers=_auth_headers(client),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["use_case_name"] == "qc_document_review"
    assert payload["document_type"] == "product_report"
    assert calls[0][1] == "qc_document_review"
    assert calls[0][0].declared_document_type == "product_report"
    assert calls[0][0].file.file_uri == "https://files.example.test/product-report.pdf"
    assert calls[0][0].source["record_id"] == "cert-product-report-001"
    assert calls[0][0].source["attachment_uuid"] == "attach-product-report-001"
    assert calls[0][0].source["sku_number"] == "1001010562202606290001"


def test_product_report_review_from_srm_returns_not_found():
    class StubSrmSqlClient:
        def fetch_all(self, sql):
            return []

    app.dependency_overrides[get_product_report_srm_sql_client] = lambda: StubSrmSqlClient()

    client = TestClient(app)
    response = client.post(
        "/api/v1/qc/product-report/reviews/from-srm",
        headers=_auth_headers(client),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "code": "PRODUCT_REPORT_SOURCE_RECORD_NOT_FOUND",
        "message": "未找到可审核的产品报告来源记录",
    }


def test_product_report_review_from_srm_rejects_missing_url():
    class StubSrmSqlClient:
        def fetch_all(self, sql):
            return [
                {
                    "uuid": "cert-product-report-001",
                    "category": "sku",
                    "typeName": "产品报告",
                    "vendorName": "广东乃一口食品有限公司",
                    "deleted": 0,
                    "removed": 0,
                }
            ]

    app.dependency_overrides[get_product_report_srm_sql_client] = lambda: StubSrmSqlClient()

    client = TestClient(app)
    response = client.post(
        "/api/v1/qc/product-report/reviews/from-srm",
        headers=_auth_headers(client),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "PRODUCT_REPORT_SOURCE_URL_MISSING",
        "message": "产品报告来源记录缺少文件 URL",
        "record_id": "cert-product-report-001",
    }


def _auth_headers(client):
    return business_license_auth_headers(client)
