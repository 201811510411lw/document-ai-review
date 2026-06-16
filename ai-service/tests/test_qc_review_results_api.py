from fastapi.testclient import TestClient

from app.api.qc_reviews import get_qc_review_repository
from app.integrations.mysql_client import MySqlSettings
from app.main import app
from app.models import ReviewDocumentInput, ReviewInput
from app.repositories.review_result_repository import MySQLReviewResultRepository
from app.services.review_service import ReviewService
from app.workflows.food_license import nodes as food_license_nodes
from app.workflows.tobacco_license import workflow as tobacco_license_workflow
from tests.mysql_repository_stub import install_mysql_repository_stub
from tests.pdf_helpers import write_minimal_pdf


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


def test_qc_review_list_queries_business_license_results_by_document_type(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = _save_business_license_review(
        tmp_path,
        monkeypatch,
        repository,
        supplier_name="成都示例商贸有限公司",
        supplier_credit_code="91510100MA0000000X",
        source_record_id="SRM-CERT-001",
    )

    app.dependency_overrides[get_qc_review_repository] = lambda: repository
    client = TestClient(app)
    response = client.get(
        "/api/v1/qc/reviews",
        params={
            "supplier_name": "成都",
            "credit_code": "91510100MA0000000X",
            "document_type": "business_license",
            "risk_level": "NONE",
            "review_status": "REVIEWED",
        },
        headers=_auth_headers(client),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0] == {
        "task_id": result.task_id,
        "use_case_name": "business_license",
        "document_type": "business_license",
        "document_type_label": "营业执照",
        "supplier_name": "成都示例商贸有限公司",
        "credit_code": "91510100MA0000000X",
        "review_status": "REVIEWED",
        "review_status_label": "已审核",
        "risk_level": "NONE",
        "risk_level_label": "无风险",
        "needs_manual_review": False,
        "summary": "营业执照规则校验通过",
        "source_record_id": "SRM-CERT-001",
        "source_attachment_ref_id": "ATT-SRM-CERT-001",
        "source_url": "https://files.example.test/SRM-CERT-001.pdf",
        "created_at": result.created_at.isoformat(),
        "updated_at": result.updated_at.isoformat(),
    }
    assert payload["metrics"]["document_type_counts"] == {"business_license": 1}


def test_qc_review_detail_reuses_business_license_evidence(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = _save_business_license_review(
        tmp_path,
        monkeypatch,
        repository,
        supplier_name="成都示例商贸有限公司",
        supplier_credit_code="91510100MA0000000X",
        source_record_id="SRM-CERT-001",
    )

    app.dependency_overrides[get_qc_review_repository] = lambda: repository
    client = TestClient(app)
    response = client.get(
        f"/api/v1/qc/reviews/{result.task_id}",
        headers=_auth_headers(client),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == result.task_id
    assert payload["document_type"] == "business_license"
    assert payload["document_type_label"] == "营业执照"
    assert payload["source_url"] == "https://files.example.test/SRM-CERT-001.pdf"
    assert payload["extracted_fields"]["subject_name"] == "成都示例商贸有限公司"
    assert payload["normalized_fields"]["credit_code"] == "91510100MA0000000X"
    assert payload["rule_results"][0]["rule_code"] == "BUSINESS_LICENSE_TYPE_MATCH"
    assert payload["manual_review"]["status"] == "NOT_REQUIRED"
    assert payload["payload"]["task_id"] == result.task_id


def test_qc_review_list_requires_login(monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    app.dependency_overrides[get_qc_review_repository] = lambda: _repository()
    client = TestClient(app)

    response = client.get("/api/v1/qc/reviews")

    assert response.status_code == 401
    assert response.json()["detail"] == {
        "code": "UNAUTHORIZED",
        "message": "请先登录工作台",
    }


def test_qc_review_list_and_detail_include_food_license_results(
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

    pdf_path = tmp_path / "food-license.pdf"
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
                file_name="food-license.pdf",
                mime_type="application/pdf",
                document_format="pdf",
                file_uri="https://files.example.test/food-license.pdf",
            ),
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_license",
            source={
                "record_id": "SRM-FOOD-001",
                "attachment_ref_id": "ATT-FOOD-001",
                "tenant": "8560",
            },
        )
    )

    app.dependency_overrides[get_qc_review_repository] = lambda: repository
    client = TestClient(app)
    list_response = client.get(
        "/api/v1/qc/reviews",
        params={"document_type": "food_license"},
        headers=_auth_headers(client),
    )
    detail_response = client.get(
        f"/api/v1/qc/reviews/{result.task_id}",
        headers=_auth_headers(client),
    )

    assert list_response.status_code == 200
    row = list_response.json()["items"][0]
    assert row["document_type"] == "food_license"
    assert row["document_type_label"] == "食品经营许可证"
    assert row["supplier_name"] == "成都示例食品有限公司"
    assert row["source_record_id"] == "SRM-FOOD-001"

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["document_type"] == "food_license"
    assert detail["source_url"] == "https://files.example.test/food-license.pdf"
    assert detail["extracted_fields"]["license_no"] == "JY15101000000000"
    assert detail["normalized_fields"]["business_items"] == ["预包装食品销售", "散装食品销售"]
    assert detail["manual_review"]["status"] == "NOT_REQUIRED"


def test_qc_manual_review_writes_food_license_decision(
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
                    "credit_code": "91510100MA99999999",
                    "license_no": "JY15101000000000",
                    "valid_to": "2028-06-05",
                },
                "metadata": {"implementation_status": "stub"},
            }

    pdf_path = tmp_path / "food-license-risk.pdf"
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
                file_name="food-license-risk.pdf",
                mime_type="application/pdf",
                document_format="pdf",
            ),
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_license",
        )
    )

    app.dependency_overrides[get_qc_review_repository] = lambda: repository
    client = TestClient(app)
    response = client.post(
        f"/api/v1/qc/reviews/{result.task_id}/manual-review",
        json={
            "decision": "approved",
            "comment": "已核对食品经营许可证原件。",
            "reviewer_id": "wecom-reviewer-001",
        },
        headers=_auth_headers(client),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["review_status"] == "MANUAL_REVIEWED"
    assert payload["needs_manual_review"] is False
    assert payload["manual_review"]["status"] == "COMPLETED"
    assert payload["manual_review"]["decision"] == "approved"
    assert payload["payload"]["status"] == "MANUAL_REVIEWED"


def test_qc_review_list_and_detail_include_product_report_results(monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = ReviewService(repository=repository).review(
        ReviewInput(
            ocr_text="""
            产品检验报告
            样品名称：麻辣牛肉
            受检单位：成都示例食品有限公司
            生产单位：成都示例食品厂
            批号：20260601-A
            生产日期：2026年06月01日
            签发日期：2026年06月10日
            检验结论：经检验，所检项目符合要求。
            检验项目：
            1. 菌落总数 120 CFU/g
            """,
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="product_report",
            source={
                "record_id": "SRM-PRODUCT-001",
                "attachment_ref_id": "ATT-PRODUCT-001",
                "tenant": "8560",
            },
        ),
        use_case_name="qc_document_review",
    )

    app.dependency_overrides[get_qc_review_repository] = lambda: repository
    client = TestClient(app)
    list_response = client.get(
        "/api/v1/qc/reviews",
        params={"document_type": "product_report"},
        headers=_auth_headers(client),
    )
    detail_response = client.get(
        f"/api/v1/qc/reviews/{result.task_id}",
        headers=_auth_headers(client),
    )

    assert list_response.status_code == 200
    row = list_response.json()["items"][0]
    assert row["document_type"] == "product_report"
    assert row["document_type_label"] == "产品报告"
    assert row["supplier_name"] == "成都示例食品有限公司"
    assert row["source_record_id"] == "SRM-PRODUCT-001"

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["document_type"] == "product_report"
    assert detail["extracted_fields"]["product_name"] == "麻辣牛肉"
    assert detail["extracted_fields"]["batch_no"] == "20260601-A"
    assert detail["extracted_fields"]["inspection_conclusion"] == "经检验，所检项目符合要求。"
    assert detail["extracted_fields"]["inspection_items"] == [
        {"name": "菌落总数", "result": "120 CFU/g"}
    ]
    assert detail["rule_results"][0]["rule_code"] == "PRODUCT_REPORT_TYPE_MATCH"


def test_qc_review_list_and_detail_include_tobacco_license_results(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()

    class StubTobaccoLicenseFileAdapter:
        def extract_text(self, source):
            return {
                "text": "",
                "structured_fields": {
                    "document_type": "tobacco_license",
                    "subject_name": "成都示例烟草商行",
                    "business_address": "成都市高新区天府大道 1 号",
                    "legal_person": "张三",
                    "license_no": "烟专零售许第510100000001号",
                    "valid_to": "2099-12-31",
                },
                "metadata": {"implementation_status": "stub"},
            }

    pdf_path = tmp_path / "tobacco-license.pdf"
    write_minimal_pdf(pdf_path, "embedded text should not be used")
    monkeypatch.setattr(
        tobacco_license_workflow,
        "tobacco_license_file_adapter",
        StubTobaccoLicenseFileAdapter(),
    )
    result = ReviewService(repository=repository).review(
        ReviewInput(
            file=ReviewDocumentInput(
                local_path=str(pdf_path),
                file_name="tobacco-license.pdf",
                mime_type="application/pdf",
                document_format="pdf",
                file_uri="https://files.example.test/tobacco-license.pdf",
            ),
            supplier_name="成都示例烟草商行",
            supplier_credit_code="91510100MA0000000X",
            declared_document_type="tobacco_license",
            source={
                "record_id": "SRM-TOBACCO-001",
                "attachment_ref_id": "ATT-TOBACCO-001",
                "tenant": "8560",
            },
        ),
        use_case_name="tobacco_license",
    )

    app.dependency_overrides[get_qc_review_repository] = lambda: repository
    client = TestClient(app)
    list_response = client.get(
        "/api/v1/qc/reviews",
        params={"document_type": "tobacco_license"},
        headers=_auth_headers(client),
    )
    detail_response = client.get(
        f"/api/v1/qc/reviews/{result.task_id}",
        headers=_auth_headers(client),
    )

    assert list_response.status_code == 200
    row = list_response.json()["items"][0]
    assert row["document_type"] == "tobacco_license"
    assert row["document_type_label"] == "烟草专卖零售许可证"
    assert row["supplier_name"] == "成都示例烟草商行"
    assert row["source_record_id"] == "SRM-TOBACCO-001"

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["document_type"] == "tobacco_license"
    assert detail["source_url"] == "https://files.example.test/tobacco-license.pdf"
    assert detail["extracted_fields"]["license_no"] == "烟专零售许第510100000001号"
    assert detail["manual_review"]["status"] == "NOT_REQUIRED"


def test_qc_review_list_and_detail_include_tobacco_consistency_results(monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = ReviewService(repository=repository).review(
        ReviewInput(
            ocr_text="structured consistency input",
            supplier_name="成都示例烟草商行",
            supplier_credit_code="91510100MA0000000X",
            declared_document_type="business_tobacco_consistency",
            source={
                "record_id": "SRM-CONSISTENCY-001",
                "attachment_ref_id": "ATT-CONSISTENCY-001",
                "tenant": "8560",
            },
            options={
                "business_license_fields": {
                    "document_type": "business_license",
                    "subject_name": "成都示例烟草商行",
                    "business_address": "成都市高新区天府大道 1 号",
                    "legal_person": "张三",
                },
                "tobacco_license_fields": {
                    "document_type": "tobacco_license",
                    "subject_name": "成都示例烟草商行",
                    "business_address": "成都市高新区天府大道 1 号",
                    "legal_person": "张三",
                    "valid_to": "2099-12-31",
                },
            },
        ),
        use_case_name="tobacco_license_consistency_review",
    )

    app.dependency_overrides[get_qc_review_repository] = lambda: repository
    client = TestClient(app)
    list_response = client.get(
        "/api/v1/qc/reviews",
        params={"document_type": "business_tobacco_consistency"},
        headers=_auth_headers(client),
    )
    detail_response = client.get(
        f"/api/v1/qc/reviews/{result.task_id}",
        headers=_auth_headers(client),
    )

    assert list_response.status_code == 200
    row = list_response.json()["items"][0]
    assert row["document_type"] == "business_tobacco_consistency"
    assert row["document_type_label"] == "营业执照与烟草证一致性"
    assert row["supplier_name"] == "成都示例烟草商行"

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["document_type"] == "business_tobacco_consistency"
    assert detail["comparison"]["differences"] == []
    assert detail["business_license_fields"]["subject_name"] == "成都示例烟草商行"
    assert detail["tobacco_license_fields"]["document_type"] == "tobacco_license"


def _save_business_license_review(
    tmp_path,
    monkeypatch,
    repository,
    *,
    supplier_name: str,
    supplier_credit_code: str,
    source_record_id: str,
):
    pdf_path = tmp_path / f"{source_record_id}.pdf"
    write_minimal_pdf(pdf_path, "embedded text should not be used")
    monkeypatch.setenv(
        "BUSINESS_LICENSE_FAKE_VISION_JSON",
        f"""
        {{
          "document_type": "business_license",
          "subject_name": "{supplier_name}",
          "credit_code": "{supplier_credit_code}",
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
                file_name=f"{source_record_id}.pdf",
                mime_type="application/pdf",
                document_format="pdf",
                file_uri=f"https://files.example.test/{source_record_id}.pdf",
            ),
            supplier_name=supplier_name,
            supplier_credit_code=supplier_credit_code,
            declared_document_type="business_license",
            source={
                "record_id": source_record_id,
                "attachment_ref_id": f"ATT-{source_record_id}",
                "tenant": "8560",
            },
        ),
        use_case_name="business_license",
    )


def _repository() -> MySQLReviewResultRepository:
    return MySQLReviewResultRepository(
        MySqlSettings(
            host="127.0.0.1",
            port=3306,
            user="review",
            password="secret",
            database="document_ai_review",
        )
    )


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "reviewer", "password": "reviewer123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
