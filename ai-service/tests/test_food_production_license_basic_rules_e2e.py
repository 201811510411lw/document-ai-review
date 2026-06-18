from datetime import date

from app.models import ReviewDocumentInput, ReviewInput
from app.services.review_service import ReviewService
from app.workflows.food_production_license import nodes as food_production_license_nodes
from tests.pdf_helpers import write_minimal_pdf


BASE_FIELDS = {
    "document_type": "food_production_license",
    "producer_name": "成都示例食品生产有限公司",
    "credit_code": "91510100MA00000000",
    "license_no": "SC10151010000000",
    "food_categories": ["糕点", "速冻食品"],
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
                "model": "fake-food-production-license-file-recognition",
            },
        }


def test_pdf_file_recognition_flow_returns_food_production_rules(tmp_path, monkeypatch):
    pdf_path = _write_pdf(tmp_path)
    adapter = StubFileAdapter(BASE_FIELDS)
    monkeypatch.setattr(
        food_production_license_nodes,
        "food_production_license_file_adapter",
        adapter,
    )

    result = ReviewService().review(
        _review_input(pdf_path),
        use_case_name="food_production_license",
    )
    payload = result.model_dump(mode="json")

    assert adapter.calls[0].content.startswith(b"%PDF-")
    assert payload["use_case_name"] == "food_production_license"
    assert payload["document_type"] == "food_production_license"
    assert payload["skill_result"]["document_input"]["input_type"] == "pdf"
    assert payload["skill_result"]["extracted_fields"]["producer_name"] == (
        "成都示例食品生产有限公司"
    )
    assert payload["risk_level"] == "NONE"
    assert payload["needs_manual_review"] is False
    assert [rule_result["rule_code"] for rule_result in payload["rule_results"]] == [
        "FOOD_PRODUCTION_LICENSE_TYPE_MATCH",
        "FOOD_PRODUCTION_LICENSE_PRODUCER_NAME_MATCH",
        "FOOD_PRODUCTION_LICENSE_CREDIT_CODE_MATCH",
        "FOOD_PRODUCTION_LICENSE_VALIDITY_PERIOD",
    ]
    assert all(rule_result["passed"] is True for rule_result in payload["rule_results"])


def test_food_production_license_chinese_document_type_and_dates_are_normalized(
    tmp_path,
    monkeypatch,
):
    pdf_path = _write_pdf(tmp_path)
    adapter = StubFileAdapter(
        {
            **BASE_FIELDS,
            "document_type": "食品生产许可证",
            "valid_from": "2023年06月05日",
            "valid_to": "2028年06月05日",
            "issue_date": "2023年06月05日",
        }
    )
    monkeypatch.setattr(
        food_production_license_nodes,
        "food_production_license_file_adapter",
        adapter,
    )

    result = ReviewService().review(
        _review_input(pdf_path),
        use_case_name="food_production_license",
    )
    payload = result.model_dump(mode="json")

    assert payload["document_type"] == "food_production_license"
    assert payload["skill_result"]["normalized_fields"]["document_type"] == (
        "food_production_license"
    )
    assert payload["skill_result"]["normalized_fields"]["valid_from"] == "2023-06-05"
    assert payload["skill_result"]["normalized_fields"]["valid_to"] == "2028-06-05"
    assert payload["skill_result"]["normalized_fields"]["issue_date"] == "2023-06-05"
    assert payload["risk_level"] == "NONE"


def test_food_production_license_producer_name_mismatch_requires_review(
    tmp_path,
    monkeypatch,
):
    pdf_path = _write_pdf(tmp_path)
    monkeypatch.setattr(
        food_production_license_nodes,
        "food_production_license_file_adapter",
        StubFileAdapter(BASE_FIELDS),
    )

    result = ReviewService().review(
        _review_input(pdf_path, supplier_name="成都另一家食品生产有限公司"),
        use_case_name="food_production_license",
    )
    payload = result.model_dump(mode="json")
    producer_rule = _rule(payload, "FOOD_PRODUCTION_LICENSE_PRODUCER_NAME_MATCH")

    assert payload["risk_level"] == "MEDIUM"
    assert payload["needs_manual_review"] is True
    assert payload["manual_review"]["reasons"] == ["生产者名称与来源信息不一致"]
    assert producer_rule["passed"] is False


def test_food_production_license_expired_is_high_risk(tmp_path, monkeypatch):
    pdf_path = _write_pdf(tmp_path)
    monkeypatch.setattr(
        food_production_license_nodes,
        "_current_rule_date",
        lambda: date(2026, 6, 9),
    )
    monkeypatch.setattr(
        food_production_license_nodes,
        "food_production_license_file_adapter",
        StubFileAdapter({**BASE_FIELDS, "valid_to": "2026-06-08"}),
    )

    result = ReviewService().review(
        _review_input(pdf_path),
        use_case_name="food_production_license",
    )
    payload = result.model_dump(mode="json")
    validity_rule = _rule(payload, "FOOD_PRODUCTION_LICENSE_VALIDITY_PERIOD")

    assert payload["risk_level"] == "HIGH"
    assert payload["needs_manual_review"] is True
    assert validity_rule["passed"] is False
    assert validity_rule["details"]["days_until_expiry"] < 0


def _write_pdf(tmp_path):
    pdf_path = tmp_path / "food-production-license.pdf"
    write_minimal_pdf(pdf_path, "embedded text should not be used")
    return pdf_path


def _review_input(
    pdf_path,
    *,
    supplier_name="成都示例食品生产有限公司",
    supplier_credit_code="91510100MA00000000",
):
    return ReviewInput(
        file=ReviewDocumentInput(
            local_path=str(pdf_path),
            file_name="food-production-license.pdf",
            mime_type="application/pdf",
            document_format="pdf",
        ),
        supplier_name=supplier_name,
        supplier_credit_code=supplier_credit_code,
        declared_document_type="food_production_license",
    )


def _rule(payload, rule_code):
    return next(
        rule_result
        for rule_result in payload["rule_results"]
        if rule_result["rule_code"] == rule_code
    )
