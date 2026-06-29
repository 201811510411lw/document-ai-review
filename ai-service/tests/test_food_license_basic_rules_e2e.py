from datetime import date

from app.models import ReviewDocumentInput, ReviewInput
from app.integrations.mysql_client import MySqlSettings
from app.repositories import MySQLReviewResultRepository
from app.services.review_service import ReviewService
from app.workflows.food_license import nodes as food_license_nodes
from tests.mysql_repository_stub import install_mysql_repository_stub
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
    assert payload["manual_review"]["reasons"] == ["主体名称与来源信息不一致"]
    assert subject_rule["passed"] is False
    assert subject_rule["risk_level_on_failure"] == "MEDIUM"


def test_food_license_subject_name_punctuation_matches_even_if_skill_flags_mismatch(
    tmp_path,
    monkeypatch,
):
    pdf_path = _write_pdf(tmp_path)
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_file_adapter",
        StubFileAdapter(
            {
                **BASE_FIELDS,
                "subject_name": "好麦多(上海)食品科技有限公司",
                "credit_code": "91310112MA1GD5WP62",
            }
        ),
    )

    class FailingSubjectRuleAdapter:
        def review(self, *, skill_name, skill_text, review_payload):
            return {
                "risk_level": "MEDIUM",
                "needs_manual_review": True,
                "summary": "主体名称不一致",
                "manual_review_reasons": ["主体名称与来源信息不一致"],
                "rule_results": [
                    {
                        "rule_code": "FOOD_LICENSE_SUBJECT_NAME_MATCH",
                        "rule_name": "主体名称是否与供应商名称一致",
                        "passed": False,
                        "risk_level_on_failure": "MEDIUM",
                        "message": "主体名称不一致。",
                        "details": {},
                    }
                ],
            }

    monkeypatch.setattr(
        food_license_nodes,
        "food_license_skill_rule_review_adapter",
        FailingSubjectRuleAdapter(),
    )

    result = ReviewService().review_food_license(
        _review_input(
            pdf_path,
            supplier_name="好麦多（上海）食品科技有限公司",
            supplier_credit_code="91310112MA1GD5WP62",
        )
    )
    payload = result.model_dump(mode="json")
    subject_rule = _rule(payload, "FOOD_LICENSE_SUBJECT_NAME_MATCH")

    assert payload["risk_level"] == "NONE"
    assert payload["needs_manual_review"] is False
    assert subject_rule["passed"] is True


def test_pdf_file_recognition_flags_credit_code_mismatch_and_saves_mysql(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    pdf_path = _write_pdf(tmp_path)
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_file_adapter",
        StubFileAdapter(BASE_FIELDS),
    )
    repository = _repository()

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


def test_food_license_credit_code_mismatch_requires_manual_review_even_if_skill_passes(
    tmp_path,
    monkeypatch,
):
    pdf_path = _write_pdf(tmp_path)
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_file_adapter",
        StubFileAdapter(
            {
                **BASE_FIELDS,
                "credit_code": "91310117MADWMPDC9C",
                "valid_to": "2030-04-08",
            }
        ),
    )

    class PassingRuleAdapter:
        def review(self, *, skill_name, skill_text, review_payload):
            return {
                "risk_level": "NONE",
                "needs_manual_review": False,
                "summary": "食品经营许可证规则校验通过",
                "manual_review_reasons": [],
                "rule_results": [
                    {
                        "rule_code": "FOOD_LICENSE_CREDIT_CODE_MATCH",
                        "rule_name": "统一社会信用代码是否与供应商一致",
                        "passed": True,
                        "risk_level_on_failure": "HIGH",
                        "message": "统一社会信用代码与供应商一致。",
                        "details": {},
                    }
                ],
            }

    monkeypatch.setattr(
        food_license_nodes,
        "food_license_skill_rule_review_adapter",
        PassingRuleAdapter(),
    )

    result = ReviewService().review_food_license(
        _review_input(pdf_path, supplier_credit_code="")
    )
    payload = result.model_dump(mode="json")
    credit_rule = _rule(payload, "FOOD_LICENSE_CREDIT_CODE_MATCH")

    assert payload["risk_level"] == "HIGH"
    assert payload["needs_manual_review"] is True
    assert "来源系统统一社会信用代码缺失" in payload["manual_review"]["reasons"]
    assert credit_rule["passed"] is False
    assert credit_rule["risk_level_on_failure"] == "HIGH"


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


def test_food_license_expired_valid_to_requires_review_even_if_skill_passes(
    tmp_path,
    monkeypatch,
):
    pdf_path = _write_pdf(tmp_path)
    monkeypatch.setattr(
        food_license_nodes,
        "_current_rule_date",
        lambda: date(2026, 6, 29),
    )
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_file_adapter",
        StubFileAdapter({**BASE_FIELDS, "valid_to": "2026-03-07"}),
    )

    class PassingRuleAdapter:
        def review(self, *, skill_name, skill_text, review_payload):
            return {
                "risk_level": "NONE",
                "needs_manual_review": False,
                "summary": "食品经营许可证规则校验通过",
                "manual_review_reasons": [],
                "rule_results": [
                    {
                        "rule_code": "FOOD_LICENSE_VALIDITY_PERIOD",
                        "rule_name": "有效期是否有效",
                        "passed": True,
                        "risk_level_on_failure": "HIGH",
                        "message": "有效期通过。",
                        "details": {},
                    }
                ],
            }

    monkeypatch.setattr(
        food_license_nodes,
        "food_license_skill_rule_review_adapter",
        PassingRuleAdapter(),
    )

    result = ReviewService().review_food_license(_review_input(pdf_path))
    payload = result.model_dump(mode="json")
    validity_rule = _rule(payload, "FOOD_LICENSE_VALIDITY_PERIOD")

    assert payload["risk_level"] == "HIGH"
    assert payload["needs_manual_review"] is True
    assert "食品经营许可证已过期" in payload["manual_review"]["reasons"]
    assert validity_rule["passed"] is False
    assert validity_rule["details"]["days_until_expiry"] < 0


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

    assert payload["risk_level"] == "HIGH"
    assert payload["needs_manual_review"] is True
    assert payload["manual_review"]["status"] == "PENDING"
    assert payload["manual_review"]["reasons"] == [
        "证照主体名称缺失，需要人工复核。",
        "证照统一社会信用代码缺失，需要人工复核。",
        "证照统一社会信用代码缺失",
    ]
    assert _rule(payload, "FOOD_LICENSE_SUBJECT_NAME_MATCH")["passed"] is False
    assert _rule(payload, "FOOD_LICENSE_CREDIT_CODE_MATCH")["passed"] is False
    validity_rule = _rule(payload, "FOOD_LICENSE_VALIDITY_PERIOD")
    assert validity_rule["passed"] is True
    assert validity_rule["details"]["assumed_long_term"] is True


def test_food_license_workflow_rejects_food_production_license_document_type(
    tmp_path,
    monkeypatch,
):
    pdf_path = _write_pdf(tmp_path)
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_file_adapter",
        StubFileAdapter(
            {
                "document_type": "食品生产许可证",
                "subject_name": "江苏香之派食品有限公司",
                "credit_code": "91321323314091953H",
                "license_no": "SC10432130000012",
                "business_address": "江苏省宿迁市泗阳县经济开发区文城东路285号",
                "valid_from": "2023年06月07日",
            }
        ),
    )

    result = ReviewService().review_food_license(
        _review_input(
            pdf_path,
            supplier_name="江苏香之派食品有限公司",
            supplier_credit_code="91321323314091953X",
        )
    )
    payload = result.model_dump(mode="json")

    assert payload["document_type"] == "food_production_license"
    assert payload["risk_level"] == "HIGH"
    assert payload["needs_manual_review"] is True
    assert payload["manual_review"]["status"] == "PENDING"
    assert "文档类型无法识别，需要人工复核" in payload["manual_review"]["reasons"]


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
