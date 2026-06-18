import importlib
from pathlib import Path

from app.models import (
    ManualReviewStatus,
    ReviewDocumentInput,
    ReviewInput,
    ReviewInputContext,
    RiskLevel,
)
from app.use_cases.food_license import use_case as food_license_use_case_module
from app.workflows.food_license import nodes as food_license_nodes
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
                "business_items": ["预包装食品销售"],
                "valid_to": "2028-06-05",
            },
            "metadata": {"implementation_status": "stub"},
        }


def test_food_license_workflow_runtime_exposes_file_review_boundary(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(food_license_nodes, "food_license_file_adapter", StubFileAdapter())
    workflow = importlib.import_module("app.workflows.food_license")

    state = workflow.run_food_license_workflow(_input_context(tmp_path))

    assert state["document_input"].input_type == "pdf"
    assert state["document_classification"].document_type == "food_license"
    assert state["risk_level"] == RiskLevel.NONE
    assert state["needs_manual_review"] is False
    assert state["manual_review"].status == ManualReviewStatus.NOT_REQUIRED


def test_food_license_use_case_facade_calls_workflow_entrypoint(tmp_path, monkeypatch):
    calls = []

    def stub_workflow(input_context):
        calls.append(input_context)
        return {
            "input_context": input_context,
            "document_classification": None,
            "extracted_fields": None,
            "normalized_fields": None,
            "rule_results": [],
            "risk_level": RiskLevel.NONE,
            "summary": "stub workflow result",
            "needs_manual_review": False,
            "manual_review": {"status": "NOT_REQUIRED"},
        }

    monkeypatch.setattr(
        food_license_use_case_module,
        "run_food_license_workflow",
        stub_workflow,
    )
    input_context = _input_context(tmp_path)

    result = food_license_use_case_module.food_license_use_case.review(input_context)

    assert calls == [input_context]
    assert result.task_id == "review-task-workflow-boundary"
    assert result.summary == "stub workflow result"


def test_platform_layer_does_not_import_food_license_workflow_nodes():
    app_root = Path(__file__).resolve().parents[1] / "app"
    platform_files = [
        *app_root.joinpath("api").glob("*.py"),
        *app_root.joinpath("services").glob("*.py"),
        app_root / "workflows" / "registry.py",
    ]

    for source_file in platform_files:
        source = source_file.read_text(encoding="utf-8")

        assert "app.workflows.food_license.nodes" not in source
        assert "app.capabilities.food_license.nodes" not in source


def _input_context(tmp_path):
    pdf_path = tmp_path / "food-license.pdf"
    write_minimal_pdf(pdf_path, "embedded text should not be used")
    return ReviewInputContext(
        task_id="review-task-workflow-boundary",
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
