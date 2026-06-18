from app.models import ReviewInputContext, ReviewResult
from app.workflows.food_production_license import run_food_production_license_workflow
from app.workflows.food_production_license.runtime import (
    food_production_license_review_state_from_workflow_state,
)
from app.workflows.runtime import ReviewRuntimeContract, review_result_from_graph_result


class FoodProductionLicenseUseCase:
    name = "food_production_license"
    version = "v1"
    ruleset_version = "food-production-license-rules-v1"
    supported_document_types = ("food_production_license",)
    runtime_contract = ReviewRuntimeContract(
        use_case_name=name,
        use_case_version=version,
        ruleset_version=ruleset_version,
        document_type="food_production_license",
        capability_names=("food_production_license",),
    )

    def supports(self, input_context: ReviewInputContext) -> bool:
        return input_context.input.declared_document_type == "food_production_license"

    def review(self, input_context: ReviewInputContext) -> ReviewResult:
        workflow_state = run_food_production_license_workflow(input_context)
        review_state = food_production_license_review_state_from_workflow_state(
            workflow_state
        )
        return review_result_from_graph_result(
            review_state,
            self.runtime_contract,
        )


food_production_license_use_case = FoodProductionLicenseUseCase()
