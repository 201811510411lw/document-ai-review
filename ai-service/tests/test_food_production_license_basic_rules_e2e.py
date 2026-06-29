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
    "legal_person": "王波",
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


def test_food_production_license_valid_from_uses_issue_date_when_equal_to_valid_to(
    tmp_path,
    monkeypatch,
):
    pdf_path = _write_pdf(tmp_path)
    adapter = StubFileAdapter(
        {
            **BASE_FIELDS,
            "valid_from": "2030-11-30",
            "valid_to": "2030年11月30日",
            "issue_date": "2025年12月01日",
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

    assert payload["skill_result"]["extracted_fields"]["valid_from"] == "2025年12月01日"
    assert payload["skill_result"]["normalized_fields"]["valid_from"] == "2025-12-01"
    assert payload["skill_result"]["normalized_fields"]["valid_to"] == "2030-11-30"
    assert payload["skill_result"]["normalized_fields"]["issue_date"] == "2025-12-01"


def test_food_production_license_missing_valid_from_uses_issue_date(
    tmp_path,
    monkeypatch,
):
    pdf_path = _write_pdf(tmp_path)
    adapter = StubFileAdapter(
        {
            **BASE_FIELDS,
            "valid_from": None,
            "valid_to": "2026年06月06日",
            "issue_date": "2024年10月18日",
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

    assert payload["skill_result"]["extracted_fields"]["valid_from"] == "2024年10月18日"
    assert payload["skill_result"]["normalized_fields"]["valid_from"] == "2024-10-18"
    assert payload["skill_result"]["normalized_fields"]["valid_to"] == "2026-06-06"
    assert payload["skill_result"]["normalized_fields"]["issue_date"] == "2024-10-18"


def test_food_production_license_valid_from_prefers_issue_date_over_ocr_value(
    tmp_path,
    monkeypatch,
):
    pdf_path = _write_pdf(tmp_path)
    adapter = StubFileAdapter(
        {
            **BASE_FIELDS,
            "valid_from": "2027年01月27日",
            "valid_to": "长期",
            "issue_date": "2022年01月28日",
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

    assert payload["skill_result"]["extracted_fields"]["valid_from"] == "2022年01月28日"
    assert payload["skill_result"]["normalized_fields"]["valid_from"] == "2022-01-28"
    assert payload["skill_result"]["extracted_fields"]["valid_to"] == "2027年01月27日"
    assert payload["skill_result"]["normalized_fields"]["valid_to"] == "2027-01-27"
    assert payload["skill_result"]["normalized_fields"]["issue_date"] == "2022-01-28"


def test_food_production_license_valid_to_uses_chinese_valid_until_alias(
    tmp_path,
    monkeypatch,
):
    pdf_path = _write_pdf(tmp_path)
    adapter = StubFileAdapter(
        {
            **BASE_FIELDS,
            "valid_to": None,
            "有效日期至": "2025年02月24日",
            "issue_date": "2023年12月26日",
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

    assert payload["skill_result"]["extracted_fields"]["valid_from"] == "2023年12月26日"
    assert payload["skill_result"]["normalized_fields"]["valid_from"] == "2023-12-26"
    assert payload["skill_result"]["extracted_fields"]["valid_to"] == "2025年02月24日"
    assert payload["skill_result"]["normalized_fields"]["valid_to"] == "2025-02-24"


def test_food_production_license_workflow_sanitizes_object_food_categories(
    tmp_path,
    monkeypatch,
):
    pdf_path = _write_pdf(tmp_path)
    adapter = StubFileAdapter(
        {
            **BASE_FIELDS,
            "food_categories": [
                {"食品类别": "糕点"},
                {"货物或应税劳务名称": "", "规格型号": ""},
            ],
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

    assert payload["skill_result"]["extracted_fields"]["food_categories"] == ["糕点"]


def test_food_production_license_workflow_sanitizes_list_scalar_fields(
    tmp_path,
    monkeypatch,
):
    pdf_path = _write_pdf(tmp_path)
    adapter = StubFileAdapter(
        {
            **BASE_FIELDS,
            "legal_person": ["王波"],
            "producer_name": ["成都示例食品生产有限公司"],
            "valid_to": ["2028-06-05"],
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

    assert payload["skill_result"]["extracted_fields"]["legal_person"] == "王波"
    assert payload["skill_result"]["extracted_fields"]["producer_name"] == (
        "成都示例食品生产有限公司"
    )
    assert payload["skill_result"]["extracted_fields"]["valid_to"] == "2028-06-05"


def test_food_production_license_legal_person_uses_chinese_alias(
    tmp_path,
    monkeypatch,
):
    pdf_path = _write_pdf(tmp_path)
    adapter = StubFileAdapter(
        {
            **BASE_FIELDS,
            "legal_person": None,
            "法定代表人": "吴守允",
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

    assert payload["skill_result"]["extracted_fields"]["legal_person"] == "吴守允"
    assert "负责人/法定代表人缺失" not in payload["manual_review"]["reasons"]


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


def test_food_production_license_credit_code_mismatch_requires_manual_review(
    tmp_path,
    monkeypatch,
):
    pdf_path = _write_pdf(tmp_path)
    monkeypatch.setattr(
        food_production_license_nodes,
        "food_production_license_file_adapter",
        StubFileAdapter({**BASE_FIELDS, "credit_code": "91321323314091953H"}),
    )

    result = ReviewService().review(
        _review_input(pdf_path, supplier_credit_code="91321323314091953X"),
        use_case_name="food_production_license",
    )
    payload = result.model_dump(mode="json")
    credit_rule = _rule(payload, "FOOD_PRODUCTION_LICENSE_CREDIT_CODE_MATCH")

    assert payload["risk_level"] == "HIGH"
    assert payload["needs_manual_review"] is True
    assert "统一社会信用代码与来源信息不一致" in payload["manual_review"]["reasons"]
    assert credit_rule["passed"] is False


def test_food_production_license_missing_source_credit_code_requires_manual_review_even_if_skill_passes(
    tmp_path,
    monkeypatch,
):
    pdf_path = _write_pdf(tmp_path)
    monkeypatch.setattr(
        food_production_license_nodes,
        "food_production_license_file_adapter",
        StubFileAdapter({**BASE_FIELDS, "credit_code": "91321323314091953H"}),
    )

    class PassingRuleAdapter:
        def review(self, *, skill_name, skill_text, review_payload):
            return {
                "risk_level": "NONE",
                "needs_manual_review": False,
                "summary": "食品生产许可证规则校验通过",
                "manual_review_reasons": [],
                "rule_results": [
                    {
                        "rule_code": "FOOD_PRODUCTION_LICENSE_CREDIT_CODE_MATCH",
                        "rule_name": "统一社会信用代码是否与供应商一致",
                        "passed": True,
                        "risk_level_on_failure": "HIGH",
                        "message": "统一社会信用代码与供应商一致。",
                        "details": {},
                    }
                ],
            }

    monkeypatch.setattr(
        food_production_license_nodes,
        "food_production_license_skill_rule_review_adapter",
        PassingRuleAdapter(),
    )

    result = ReviewService().review(
        _review_input(pdf_path, supplier_credit_code=""),
        use_case_name="food_production_license",
    )
    payload = result.model_dump(mode="json")
    credit_rule = _rule(payload, "FOOD_PRODUCTION_LICENSE_CREDIT_CODE_MATCH")

    assert payload["risk_level"] == "HIGH"
    assert payload["needs_manual_review"] is True
    assert "来源系统统一社会信用代码缺失" in payload["manual_review"]["reasons"]
    assert credit_rule["passed"] is False
    assert credit_rule["risk_level_on_failure"] == "HIGH"


def test_food_production_license_missing_visible_key_fields_requires_manual_review(
    tmp_path,
    monkeypatch,
):
    pdf_path = _write_pdf(tmp_path)
    monkeypatch.setattr(
        food_production_license_nodes,
        "food_production_license_file_adapter",
        StubFileAdapter(
            {
                **BASE_FIELDS,
                "legal_person": None,
                "valid_to": None,
            }
        ),
    )

    result = ReviewService().review(
        _review_input(pdf_path),
        use_case_name="food_production_license",
    )
    payload = result.model_dump(mode="json")

    assert payload["risk_level"] == "HIGH"
    assert payload["needs_manual_review"] is True
    assert "负责人/法定代表人缺失" in payload["manual_review"]["reasons"]
    assert "有效期截止日期缺失" in payload["manual_review"]["reasons"]


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
