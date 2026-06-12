from datetime import date

from app.models import ReviewDocumentInput, ReviewInput
from app.repositories import SQLiteReviewResultRepository
from app.services.review_service import ReviewService
from app.workflows.food_license import nodes as food_license_nodes
from tests.pdf_helpers import write_minimal_pdf


BASE_FIELDS = {
    "document_type": "food_license",
    "subject_name": "成都示例食品有限公司",
    "credit_code": "91510100MA00000000",
    "license_no": "JY15101000000000",
    "business_items": ["预包装食品销售", "散装食品销售"],
    "valid_to": "2028-06-05",
}


class StubFileAdapter:
    def __init__(self, fields):
        self.fields = fields
        self.calls = []

    def extract_text(self, source):
        self.calls.append(source)
        return {
            "text": "",
            "structured_fields": self.fields,
            "metadata": {
                "implementation_status": "stub",
                "provider": "fake",
                "model": "fake-food-license-file-recognition",
            },
        }


def test_pdf_file_recognition_flow_returns_basic_rule_results_and_no_risk(
    tmp_path,
    monkeypatch,
):
    pdf_path = _write_pdf(tmp_path)
    adapter = StubFileAdapter(BASE_FIELDS)
    monkeypatch.setattr(food_license_nodes, "food_license_file_adapter", adapter)

    result = ReviewService().review_food_license(
        _review_input(pdf_path, supplier_name="成都示例食品有限公司")
    )
    payload = result.model_dump(mode="json")

    assert adapter.calls[0].content.startswith(b"%PDF-")
    assert adapter.calls[0].mime_type == "application/pdf"
    assert payload["skill_result"]["document_input"]["input_type"] == "pdf"
    assert payload["skill_result"]["extraction_metadata"]["structured_extraction"] == {
        "source": "llm_file_extractor",
        "schema": "FoodLicenseExtractedFields",
    }
    assert payload["risk_level"] == "NONE"
    assert payload["needs_manual_review"] is False
    assert payload["manual_review"]["status"] == "NOT_REQUIRED"
    assert [rule_result["rule_code"] for rule_result in payload["rule_results"]] == [
        "FOOD_LICENSE_RULE_ENGINE_STUB",
        "FOOD_LICENSE_TYPE_MATCH",
        "FOOD_LICENSE_SUBJECT_NAME_MATCH",
        "FOOD_LICENSE_CREDIT_CODE_MATCH",
        "FOOD_LICENSE_VALIDITY_PERIOD",
    ]
    assert all(rule_result["passed"] is True for rule_result in payload["rule_results"])


def test_file_recognition_fields_drive_subject_name_manual_review(
    tmp_path,
    monkeypatch,
):
    pdf_path = _write_pdf(tmp_path)
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_file_adapter",
        StubFileAdapter(BASE_FIELDS),
    )

    result = ReviewService().review_food_license(
        _review_input(pdf_path, supplier_name="成都另一家食品有限公司")
    )
    payload = result.model_dump(mode="json")
    subject_rule = _rule(payload, "FOOD_LICENSE_SUBJECT_NAME_MATCH")

    assert payload["risk_level"] == "MEDIUM"
    assert payload["needs_manual_review"] is True
    assert payload["manual_review"]["status"] == "PENDING"
    assert payload["manual_review"]["reasons"] == ["确定性规则结果需要人工复核"]
    assert subject_rule["passed"] is False
    assert subject_rule["risk_level_on_failure"] == "MEDIUM"


def test_pdf_file_recognition_flags_credit_code_mismatch_and_saves_sqlite(
    tmp_path,
    monkeypatch,
):
    pdf_path = _write_pdf(tmp_path)
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_file_adapter",
        StubFileAdapter(BASE_FIELDS),
    )
    repository = SQLiteReviewResultRepository(tmp_path / "reviews.sqlite3")

    result = ReviewService(repository=repository).review_food_license(
        _review_input(pdf_path, supplier_credit_code="91510100MA99999999")
    )
    payload = result.model_dump(mode="json")
    credit_rule = _rule(payload, "FOOD_LICENSE_CREDIT_CODE_MATCH")
    loaded = repository.get_by_task_id(result.task_id)

    assert "pdf_loader" not in payload["skill_result"]["extraction_metadata"]
    assert payload["risk_level"] == "HIGH"
    assert payload["needs_manual_review"] is True
    assert credit_rule["passed"] is False
    assert credit_rule["risk_level_on_failure"] == "HIGH"
    assert loaded is not None
    assert loaded.model_dump(mode="json") == payload


def test_file_recognition_expired_license_is_high_risk(tmp_path, monkeypatch):
    pdf_path = _write_pdf(tmp_path)
    monkeypatch.setattr(
        food_license_nodes,
        "_current_rule_date",
        lambda: date(2026, 6, 9),
    )
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_file_adapter",
        StubFileAdapter({**BASE_FIELDS, "valid_to": "2026-06-08"}),
    )

    result = ReviewService().review_food_license(_review_input(pdf_path))
    payload = result.model_dump(mode="json")
    validity_rule = _rule(payload, "FOOD_LICENSE_VALIDITY_PERIOD")

    assert payload["risk_level"] == "HIGH"
    assert payload["needs_manual_review"] is True
    assert validity_rule["passed"] is False
    assert validity_rule["risk_level_on_failure"] == "HIGH"
    assert validity_rule["details"]["days_until_expiry"] < 0


def test_file_recognition_license_expiring_within_thirty_days_is_medium_risk(
    tmp_path,
    monkeypatch,
):
    pdf_path = _write_pdf(tmp_path)
    monkeypatch.setattr(
        food_license_nodes,
        "_current_rule_date",
        lambda: date(2026, 6, 9),
    )
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_file_adapter",
        StubFileAdapter({**BASE_FIELDS, "valid_to": "2026-07-09"}),
    )

    result = ReviewService().review_food_license(_review_input(pdf_path))
    payload = result.model_dump(mode="json")
    validity_rule = _rule(payload, "FOOD_LICENSE_VALIDITY_PERIOD")

    assert payload["risk_level"] == "MEDIUM"
    assert payload["needs_manual_review"] is True
    assert validity_rule["passed"] is False
    assert validity_rule["risk_level_on_failure"] == "MEDIUM"
    assert validity_rule["details"]["days_until_expiry"] <= 30


def test_file_recognition_missing_fields_enter_manual_review_without_model_decision(
    tmp_path,
    monkeypatch,
):
    pdf_path = _write_pdf(tmp_path)
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_file_adapter",
        StubFileAdapter(
            {
                "document_type": "food_license",
                "license_no": "JY15101000000000",
            }
        ),
    )

    result = ReviewService().review_food_license(_review_input(pdf_path))
    payload = result.model_dump(mode="json")

    assert payload["risk_level"] == "NONE"
    assert payload["needs_manual_review"] is True
    assert payload["manual_review"]["status"] == "PENDING"
    assert payload["manual_review"]["reasons"] == ["规则执行异常或不完整，需要人工复核"]
    assert _rule(payload, "FOOD_LICENSE_SUBJECT_NAME_MATCH")["details"]["status"] == "error"
    assert _rule(payload, "FOOD_LICENSE_CREDIT_CODE_MATCH")["details"]["status"] == "error"
    assert _rule(payload, "FOOD_LICENSE_VALIDITY_PERIOD")["details"]["status"] == "error"


def _write_pdf(tmp_path):
    pdf_path = tmp_path / "food-license.pdf"
    write_minimal_pdf(pdf_path, "embedded text should not be used")
    return pdf_path


def _review_input(
    pdf_path,
    *,
    supplier_name="成都示例食品有限公司",
    supplier_credit_code="91510100MA00000000",
):
    return ReviewInput(
        file=ReviewDocumentInput(
            local_path=str(pdf_path),
            file_name="food-license.pdf",
            mime_type="application/pdf",
            document_format="pdf",
        ),
        supplier_name=supplier_name,
        supplier_credit_code=supplier_credit_code,
        declared_document_type="food_license",
    )


def _rule(payload, rule_code):
    return next(
        rule_result
        for rule_result in payload["rule_results"]
        if rule_result["rule_code"] == rule_code
    )
