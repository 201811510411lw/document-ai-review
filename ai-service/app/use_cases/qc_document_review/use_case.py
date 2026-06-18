from app.models import ReviewInputContext, ReviewResult
from app.workflows.runtime import ReviewRuntimeContract, review_result_from_graph_result
from app.workflows.qc_document import run_qc_document_workflow
from app.workflows.qc_document.runtime import qc_document_review_state_from_workflow_state


class QcDocumentReviewUseCase:
    name = "qc_document_review"
    version = "v1"
    ruleset_version = "qc-document-rules-v1"
    supported_document_types = (
        "qc_document_review",
        "qc_document",
        "batch_report",
        "third_party_inspection_report",
        "product_report",
    )
    runtime_contract = ReviewRuntimeContract(
        use_case_name=name,
        use_case_version=version,
        ruleset_version=ruleset_version,
        document_type="qc_document",
        capability_names=("qc_document_review", "product_report"),
    )

    def supports(self, input_context: ReviewInputContext) -> bool:
        return input_context.input.declared_document_type in self.supported_document_types

    def review(self, input_context: ReviewInputContext) -> ReviewResult:
        workflow_result = run_qc_document_workflow(input_context)
        review_state = qc_document_review_state_from_workflow_state(workflow_result)
        return review_result_from_graph_result(
            review_state,
            self.runtime_contract,
        )


qc_document_review_use_case = QcDocumentReviewUseCase()
