from fastapi.testclient import TestClient

from app.api.qc_reviews import (
    get_batch_report_starrocks_sql_client,
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


def test_batch_report_review_from_starrocks_routes_to_qc_document_review():
    calls = []

    class StubStarRocksClient:
        def fetch_all(self, sql):
            assert "2026-05-05 00:00:00" in sql
            return [
                {
                    "order_uuid": "order-001",
                    "order_number": "10102605050385",
                    "order_tenant": "8560",
                    "order_state": "finish",
                    "order_type": "自营进",
                    "order_biz_type": "0",
                    "order_created": "2026-05-05 16:43:01",
                    "vendor_id": "VENDOR-001",
                    "vendor_name": "广州市秀雅秀贸易有限公司（常温）",
                    "batch_uuid": "batch-001",
                    "orderline_uuid": "line-001",
                    "sku_code": "10080788",
                    "barcode": "6959011900929",
                    "sku_name": "游世佳族金唱片面包",
                    "production_time": "2026-05-08 00:00:00",
                    "expired_time": "2026-08-06 00:00:00",
                    "attachment_uuid": "attach-001",
                    "attachment_ref_id": "batch-001",
                    "attachment_ref_type": "orderDeliveryBatch",
                    "attachment_name": "金唱片面包20260508.pdf",
                    "attachment_store_id": "oss-key",
                    "attachment_url": "https://files.example.test/batch-report.pdf",
                }
            ]

    class StubReviewService(ReviewService):
        def review(self, review_input, *, use_case_name=None) -> ReviewResult:
            calls.append((review_input, use_case_name))
            return super().review(
                review_input.model_copy(
                    update={
                        "ocr_text": """
                        商品批次报告
                        厂名：广州市秀雅秀贸易有限公司（常温）
                        产品名称：游世佳族金唱片面包
                        生产日期：2026年05月08日
                        """
                    }
                ),
                use_case_name=use_case_name,
            )

    app.dependency_overrides[get_batch_report_starrocks_sql_client] = (
        lambda: StubStarRocksClient()
    )
    app.dependency_overrides[get_review_service] = lambda: StubReviewService()

    client = TestClient(app)
    response = client.post(
        "/api/v1/qc/batch-report/reviews/from-starrocks",
        headers=_auth_headers(client),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["use_case_name"] == "qc_document_review"
    assert payload["document_type"] == "batch_report"
    assert payload["status"] == "REVIEWED"
    assert calls[0][1] == "qc_document_review"
    assert calls[0][0].declared_document_type == "batch_report"
    assert calls[0][0].source["order_number"] == "10102605050385"
    assert calls[0][0].source["production_date"] == "2026-05-08"


def test_batch_report_review_from_starrocks_returns_not_found():
    class StubStarRocksClient:
        def fetch_all(self, sql):
            return []

    app.dependency_overrides[get_batch_report_starrocks_sql_client] = (
        lambda: StubStarRocksClient()
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/qc/batch-report/reviews/from-starrocks",
        headers=_auth_headers(client),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "code": "BATCH_REPORT_SOURCE_RECORD_NOT_FOUND",
        "message": "未找到可审核的商品批次报告来源记录",
        "review_date": "2026-05-05",
    }


def test_batch_report_review_from_starrocks_accepts_review_date_query():
    class StubStarRocksClient:
        def fetch_all(self, sql):
            assert "2026-05-06 00:00:00" in sql
            assert "2026-05-07 00:00:00" in sql
            return []

    app.dependency_overrides[get_batch_report_starrocks_sql_client] = (
        lambda: StubStarRocksClient()
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/qc/batch-report/reviews/from-starrocks?review_date=2026-05-06",
        headers=_auth_headers(client),
    )

    assert response.status_code == 404
    assert response.json()["detail"]["review_date"] == "2026-05-06"


def _auth_headers(client):
    return business_license_auth_headers(client)
