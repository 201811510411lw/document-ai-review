from app.models import ReviewInputContext, ReviewResult
from app.workflows.business_license import run_business_license_workflow
from app.workflows.business_license.runtime import (
    business_license_review_state_from_workflow_state,
)
from app.workflows.runtime import ReviewRuntimeContract, review_result_from_graph_result


class BusinessLicenseUseCase:
    name = "business_license"
    version = "v1"
    ruleset_version = "business-license-rules-v1"
    supported_document_types = ("business_license",)
    runtime_contract = ReviewRuntimeContract(
        use_case_name=name,
        use_case_version=version,
        ruleset_version=ruleset_version,
        document_type="business_license",
        capability_names=("business_license",),
    )

    def supports(self, input_context: ReviewInputContext) -> bool:
        return input_context.input.declared_document_type in self.supported_document_types

    def review(self, input_context: ReviewInputContext) -> ReviewResult:
        workflow_state = run_business_license_workflow(input_context)
        review_state = business_license_review_state_from_workflow_state(workflow_state)
        return review_result_from_graph_result(
            review_state,
            self.runtime_contract,
        )


business_license_use_case = BusinessLicenseUseCase()
