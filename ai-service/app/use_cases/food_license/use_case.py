from app.models import ReviewInputContext, ReviewResult
from app.workflows.food_license import run_food_license_workflow
from app.workflows.food_license.runtime import food_license_review_state_from_workflow_state
from app.workflows.runtime import ReviewRuntimeContract, review_result_from_graph_result


class FoodLicenseUseCase:
    name = "food_license"
    version = "v1"
    ruleset_version = "food-license-rules-v1"
    supported_document_types = ("food_license",)
    runtime_contract = ReviewRuntimeContract(
        use_case_name=name,
        use_case_version=version,
        ruleset_version=ruleset_version,
        document_type="food_license",
        capability_names=("food_license",),
    )

    def supports(self, input_context: ReviewInputContext) -> bool:
        declared_document_type = input_context.input.declared_document_type
        return declared_document_type in (None, "food_license")

    def review(self, input_context: ReviewInputContext) -> ReviewResult:
        workflow_state = run_food_license_workflow(input_context)
        review_state = food_license_review_state_from_workflow_state(workflow_state)
        return review_result_from_graph_result(
            review_state,
            self.runtime_contract,
        )


food_license_use_case = FoodLicenseUseCase()
