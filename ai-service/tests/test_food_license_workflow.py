from app.models import (
    ManualReviewStatus,
    ReviewDocumentInput,
    ReviewInput,
    ReviewInputContext,
    ReviewResult,
    ReviewStatus,
    RiskLevel,
)
from app.use_cases.food_license.use_case import food_license_use_case
from app.workflows.food_license import nodes as food_license_nodes
from app.workflows.food_license import run_food_license_workflow
from tests.pdf_helpers import write_minimal_pdf


FIELDS = {
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

    def extract_text(self, source):
        return {
            "text": "",
            "structured_fields": self.fields,
            "metadata": {"implementation_status": "stub"},
        }


def test_food_license_use_case_review_extracts_fields_from_file_and_returns_review_result(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_file_adapter",
        StubFileAdapter(FIELDS),
    )
    input_context = _input_context(tmp_path)

    result = food_license_use_case.review(input_context)
    payload = result.model_dump(mode="json")

    assert isinstance(result, ReviewResult)
    assert result.task_id == "review-task-001"
    assert result.skill_name == "food_license"
    assert result.skill_version == "v1"
    assert result.ruleset_version == "food-license-rules-v1"
    assert result.document_type == "food_license"
    assert result.status == ReviewStatus.REVIEWED
    assert result.risk_level == RiskLevel.NONE
    assert result.needs_manual_review is False
    assert result.manual_review.status == ManualReviewStatus.NOT_REQUIRED
    assert result.audit_events

    assert "extracted_fields" not in payload
    assert "normalized_fields" not in payload
    assert "document_classification" not in payload
    assert payload["skill_result"]["document_classification"] == {
        "document_type": "food_license",
        "confidence": 1.0,
        "reasons": ["大模型文件识别返回结构化证照类型"],
    }
    extracted_fields = payload["skill_result"]["extracted_fields"]
    normalized_fields = payload["skill_result"]["normalized_fields"]
    assert extracted_fields["subject_name"] == "成都示例食品有限公司"
    assert extracted_fields["credit_code"] == "91510100MA00000000"
    assert extracted_fields["license_no"] == "JY15101000000000"
    assert extracted_fields["business_items"] == ["预包装食品销售", "散装食品销售"]
    assert extracted_fields["valid_to"] == "2028-06-05"
    assert normalized_fields["license_no"] == "JY15101000000000"
    assert payload["rule_results"][0]["rule_code"] == "FOOD_LICENSE_RULE_ENGINE_STUB"


def test_food_license_workflow_public_entrypoint_runs_rules_after_file_recognition(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_file_adapter",
        StubFileAdapter(FIELDS),
    )

    state = run_food_license_workflow(_input_context(tmp_path))

    assert state["document_input"].input_type == "pdf"
    assert state["document_classification"].document_type == "food_license"
    assert len(state["rule_results"]) == 5
    assert [rule_result.rule_code for rule_result in state["rule_results"]] == [
        "FOOD_LICENSE_RULE_ENGINE_STUB",
        "FOOD_LICENSE_TYPE_MATCH",
        "FOOD_LICENSE_SUBJECT_NAME_MATCH",
        "FOOD_LICENSE_CREDIT_CODE_MATCH",
        "FOOD_LICENSE_VALIDITY_PERIOD",
    ]
    assert all(rule_result.passed is True for rule_result in state["rule_results"])
    assert state["risk_level"] == RiskLevel.NONE
    assert state["needs_manual_review"] is False


def test_unknown_file_recognition_document_type_requires_manual_review(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_file_adapter",
        StubFileAdapter({"document_type": "business_license"}),
    )

    result = food_license_use_case.review(_input_context(tmp_path))
    payload = result.model_dump(mode="json")

    assert payload["skill_result"]["document_classification"]["document_type"] == "business_license"
    assert result.risk_level == RiskLevel.HIGH
    assert result.needs_manual_review is True
    assert result.manual_review.status == ManualReviewStatus.PENDING
    assert result.manual_review.reasons == ["文档类型无法识别，需要人工复核"]
    assert payload["rule_results"][1]["rule_code"] == "FOOD_LICENSE_TYPE_MATCH"
    assert payload["rule_results"][1]["passed"] is False


def test_food_license_workflow_normalizes_chinese_document_type_and_dates(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_file_adapter",
        StubFileAdapter(
            {
                **FIELDS,
                "document_type": "食品经营许可证",
                "valid_from": "2020年10月19日",
                "valid_to": "2025年10月18日",
                "issue_date": "2020年10月19日",
            }
        ),
    )

    state = run_food_license_workflow(_input_context(tmp_path))

    assert state["document_classification"].document_type == "food_license"
    assert state["document_classification"].confidence == 1.0
    assert state["normalized_fields"].valid_from == "2020-10-19"
    assert state["normalized_fields"].valid_to == "2025-10-18"
    assert state["normalized_fields"].issue_date == "2020-10-19"
    assert state["manual_review"].reasons != ["文档类型无法识别，需要人工复核"]


def _input_context(tmp_path):
    pdf_path = tmp_path / "food-license.pdf"
    write_minimal_pdf(pdf_path, "embedded text should not be used")
    return ReviewInputContext(
        task_id="review-task-001",
        input=ReviewInput(
            file=ReviewDocumentInput(
                local_path=str(pdf_path),
                file_name="food-license.pdf",
                mime_type="application/pdf",
                document_format="pdf",
            ),
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_license",
        ),
        skill_name="food_license",
        skill_version="v1",
        ruleset_version="food-license-rules-v1",
    )
