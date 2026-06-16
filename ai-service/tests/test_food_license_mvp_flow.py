from app.models import ReviewDocumentInput, ReviewInput
from app.integrations.mysql_client import MySqlSettings
from app.repositories import MySQLReviewResultRepository
from app.services.review_service import ReviewService
from app.workflows.food_license import nodes as food_license_nodes
from tests.mysql_repository_stub import install_mysql_repository_stub
from tests.pdf_helpers import write_minimal_pdf


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
                "implementation_status": "stub",
                "provider": "fake",
                "model": "fake-food-license-file-recognition",
            },
        }


def test_food_license_mvp_review_flow_can_save_pdf_file_recognition_result(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    monkeypatch.setattr(food_license_nodes, "food_license_file_adapter", StubFileAdapter())
    pdf_path = tmp_path / "food-license.pdf"
    write_minimal_pdf(pdf_path, "embedded text should not be used")
    repository = _repository()
    service = ReviewService(repository=repository)

    result = service.review_food_license(
        ReviewInput(
            file=ReviewDocumentInput(
                local_path=str(pdf_path),
                file_name="food-license.pdf",
                mime_type="application/pdf",
                document_format="pdf",
            ),
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_license",
        )
    )
    payload = result.model_dump(mode="json")

    assert payload["skill_result"]["document_input"]["input_type"] == "pdf"
    assert payload["skill_result"]["document_classification"]["document_type"] == "food_license"
    assert payload["skill_result"]["extracted_fields"]["license_no"] == "JY15101000000000"
    assert payload["skill_result"]["extraction_metadata"]["llm_file_extractor"][
        "implementation_status"
    ] == "stub"
    assert [rule_result["rule_code"] for rule_result in payload["rule_results"]] == [
        "FOOD_LICENSE_RULE_ENGINE_STUB",
        "FOOD_LICENSE_TYPE_MATCH",
        "FOOD_LICENSE_SUBJECT_NAME_MATCH",
        "FOOD_LICENSE_CREDIT_CODE_MATCH",
        "FOOD_LICENSE_VALIDITY_PERIOD",
    ]
    assert all(rule_result["passed"] is True for rule_result in payload["rule_results"])
    assert payload["risk_level"] == "NONE"
    assert payload["needs_manual_review"] is False
    loaded = repository.get_by_task_id(result.task_id)
    assert loaded is not None
    assert loaded.model_dump(mode="json") == result.model_dump(mode="json")


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
