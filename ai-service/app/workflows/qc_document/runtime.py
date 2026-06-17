from app.models import ManualReview, ManualReviewStatus, ReviewStatus, RiskLevel
from app.workflows.runtime import ReviewDecision, ReviewState


def qc_document_review_state_from_workflow_state(workflow_state: dict) -> ReviewState:
    skill_result = workflow_state.get("skill_result", workflow_state)
    needs_manual_review = workflow_state.get("needs_manual_review", True)
    status = ReviewStatus(workflow_state.get("status", ReviewStatus.PENDING_MANUAL_REVIEW))
    risk_level = RiskLevel(workflow_state.get("risk_level", RiskLevel.MEDIUM))

    return {
        "input_context": workflow_state["input_context"],
        "document": {
            "document_type": workflow_state.get("document_type")
            or workflow_state["input_context"].input.declared_document_type
            or "qc_document",
        },
        "extracted_fields": skill_result.get("extracted_fields", {}),
        "normalized_fields": skill_result.get("extracted_fields", {}),
        "rule_results": workflow_state.get("rule_results", []),
        "risk_level": risk_level,
        "decision": _decision_from_status(status, needs_manual_review),
        "needs_manual_review": needs_manual_review,
        "manual_review": workflow_state.get(
            "manual_review",
            ManualReview(
                status=(
                    ManualReviewStatus.PENDING
                    if needs_manual_review
                    else ManualReviewStatus.NOT_REQUIRED
                )
            ),
        ),
        "manual_review_reasons": list(
            getattr(workflow_state.get("manual_review"), "reasons", []) or []
        ),
        "summary": workflow_state.get(
            "summary",
            "qc_document_review 返回了未完整的审核结果。",
        ),
        "status": status,
        "artifacts": {
            "implementation_status": workflow_state.get(
                "implementation_status",
                "implemented",
            ),
            "capability_names": workflow_state.get("capability_names", []),
            **skill_result,
        },
    }


def _decision_from_status(
    status: ReviewStatus,
    needs_manual_review: bool,
) -> ReviewDecision:
    if status == ReviewStatus.FAILED:
        return ReviewDecision.REJECTED
    if needs_manual_review:
        return ReviewDecision.MANUAL_REVIEW
    return ReviewDecision.REVIEWED
