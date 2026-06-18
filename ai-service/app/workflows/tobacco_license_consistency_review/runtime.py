from app.models import ManualReview, ManualReviewStatus, ReviewStatus
from app.workflows.runtime import ReviewDecision, ReviewState


def tobacco_license_consistency_review_state_from_workflow_state(
    workflow_state: dict,
) -> ReviewState:
    needs_manual_review = workflow_state.get("needs_manual_review", True)
    return {
        "input_context": workflow_state["input_context"],
        "document": {"document_type": "business_tobacco_consistency"},
        "extracted_fields": {
            "business_license": workflow_state.get("business_license_fields", {}),
            "tobacco_license": workflow_state.get("tobacco_license_fields", {}),
        },
        "normalized_fields": workflow_state.get("comparison", {}),
        "rule_results": workflow_state.get("rule_results", []),
        "risk_level": workflow_state.get("risk_level"),
        "decision": (
            ReviewDecision.MANUAL_REVIEW
            if needs_manual_review
            else ReviewDecision.REVIEWED
        ),
        "needs_manual_review": needs_manual_review,
        "manual_review": ManualReview(
            status=(
                ManualReviewStatus.PENDING
                if needs_manual_review
                else ManualReviewStatus.NOT_REQUIRED
            ),
            reasons=workflow_state.get("manual_review_reasons", []),
        ),
        "manual_review_reasons": workflow_state.get("manual_review_reasons", []),
        "summary": workflow_state.get("summary", "营业执照与烟草证一致性审核结果不完整。"),
        "status": (
            ReviewStatus.PENDING_MANUAL_REVIEW
            if needs_manual_review
            else ReviewStatus.REVIEWED
        ),
        "artifacts": {
            "implementation_status": "implemented",
            "business_license_fields": workflow_state.get("business_license_fields", {}),
            "tobacco_license_fields": workflow_state.get("tobacco_license_fields", {}),
            "comparison": workflow_state.get("comparison", {}),
            "source_evidence": workflow_state.get("source_evidence", {}),
        },
    }
