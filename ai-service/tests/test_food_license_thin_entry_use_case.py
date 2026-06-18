from app.models import (
    ManualReview,
    ManualReviewStatus,
    ReviewInput,
    ReviewInputContext,
    RiskLevel,
)
from app.use_cases.food_license import use_case as food_license_use_case_module
from app.use_cases.food_license.use_case import FoodLicenseUseCase


def test_food_license_use_case_is_thin_entry_over_runtime_contract(monkeypatch):
    def stub_workflow(input_context):
        return {
            "input_context": input_context,
            "document": {"document_type": "food_license"},
            "extracted_fields": {
                "document_type": "food_license",
                "subject_name": "成都示例食品有限公司",
            },
            "normalized_fields": {
                "document_type": "food_license",
                "subject_name": "成都示例食品有限公司",
            },
            "risk_level": RiskLevel.NONE,
            "needs_manual_review": False,
            "manual_review": ManualReview(status=ManualReviewStatus.NOT_REQUIRED),
            "summary": "食品经营许可证规则校验通过",
            "artifacts": {"document_input": {"file_name": "food-license.pdf"}},
        }

    monkeypatch.setattr(
        food_license_use_case_module,
        "run_food_license_workflow",
        stub_workflow,
    )
    assert not hasattr(
        food_license_use_case_module,
        "build_food_license_capability_result",
    )
    input_context = ReviewInputContext(
        task_id="review-task-food-thin-entry",
        input=ReviewInput(
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_license",
        ),
        use_case_name="food_license",
        use_case_version="v1",
        ruleset_version="food-license-rules-v1",
    )

    result = FoodLicenseUseCase().review(input_context)

    assert result.use_case_name == "food_license"
    assert result.capability_names == ["food_license"]
    assert result.document_type == "food_license"
    assert result.risk_level == RiskLevel.NONE
    assert result.skill_result["document_input"]["file_name"] == "food-license.pdf"
