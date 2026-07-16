from app.models import ReviewInputContext, ReviewResult
from app.workflows.runtime import ReviewRuntimeContract, review_result_from_graph_result
from app.workflows.tobacco_license_consistency_review import (
    run_tobacco_license_consistency_workflow,
)
from app.workflows.tobacco_license_consistency_review.runtime import (
    tobacco_license_consistency_review_state_from_workflow_state,
)


class TobaccoLicenseConsistencyReviewUseCase:
    name = "tobacco_license_consistency_review"
    version = "v1"
    ruleset_version = "tobacco-license-consistency-rules-v2"
    supported_document_types = (
        "tobacco_license_consistency_review",
        "tobacco_license_consistency",
        "business_tobacco_consistency",
    )
    runtime_contract = ReviewRuntimeContract(
        use_case_name=name,
        use_case_version=version,
        ruleset_version=ruleset_version,
        document_type="business_tobacco_consistency",
        capability_names=(
            "business_license",
            "tobacco_license",
            "tobacco_license_consistency",
        ),
    )

    def supports(self, input_context: ReviewInputContext) -> bool:
        return input_context.input.declared_document_type in self.supported_document_types

    def review(self, input_context: ReviewInputContext) -> ReviewResult:
        workflow_state = run_tobacco_license_consistency_workflow(input_context)
        review_state = tobacco_license_consistency_review_state_from_workflow_state(
            workflow_state
        )
        return review_result_from_graph_result(
            review_state,
            self.runtime_contract,
        )


tobacco_license_consistency_review_use_case = TobaccoLicenseConsistencyReviewUseCase()
