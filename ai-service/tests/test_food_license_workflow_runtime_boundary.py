import importlib
from pathlib import Path

from app.models import (
    ManualReviewStatus,
    ReviewInput,
    ReviewInputContext,
    RiskLevel,
)
from app.skills.food_license import skill as food_license_skill_module


def test_food_license_workflow_runtime_exposes_review_boundary():
    workflow = importlib.import_module("app.workflows.food_license")
    input_context = ReviewInputContext(
        task_id="review-task-workflow-boundary",
        input=ReviewInput(
            ocr_text="食品经营许可证\n许可证编号：JY15101000000000",
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_license",
        ),
        skill_name="food_license",
        skill_version="v1",
        ruleset_version="food-license-rules-v1",
    )

    state = workflow.run_food_license_workflow(input_context)

    assert state["document_classification"].document_type == "food_license"
    assert state["risk_level"] == RiskLevel.NONE
    assert state["needs_manual_review"] is False
    assert state["manual_review"].status == ManualReviewStatus.NOT_REQUIRED


def test_food_license_skill_facade_calls_workflow_entrypoint(monkeypatch):
    calls = []

    def stub_workflow(input_context):
        calls.append(input_context)
        return {
            "document_classification": None,
            "extracted_fields": None,
            "normalized_fields": None,
            "rule_results": [],
            "risk_level": RiskLevel.NONE,
            "summary": "stub workflow result",
            "needs_manual_review": False,
            "manual_review": {"status": "NOT_REQUIRED"},
        }

    monkeypatch.setattr(food_license_skill_module, "run_food_license_workflow", stub_workflow)
    input_context = ReviewInputContext(
        task_id="review-task-skill-facade",
        input=ReviewInput(
            ocr_text="食品经营许可证",
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_license",
        ),
        skill_name="food_license",
        skill_version="v1",
        ruleset_version="food-license-rules-v1",
    )

    result = food_license_skill_module.food_license_skill.review(input_context)

    assert calls == [input_context]
    assert result.task_id == "review-task-skill-facade"
    assert result.summary == "stub workflow result"


def test_platform_layer_does_not_import_food_license_workflow_nodes():
    app_root = Path(__file__).resolve().parents[1] / "app"
    platform_files = [
        *app_root.joinpath("api").glob("*.py"),
        *app_root.joinpath("services").glob("*.py"),
        app_root / "skills" / "registry.py",
    ]

    for source_file in platform_files:
        source = source_file.read_text(encoding="utf-8")

        assert "app.workflows.food_license.nodes" not in source
        assert "app.skills.food_license.nodes" not in source
