from typing import Any

from pydantic import BaseModel

from app.models import ReviewStatus
from app.workflows.runtime import ReviewDecision, ReviewState


def food_production_license_review_state_from_workflow_state(
    workflow_state: dict[str, Any],
) -> ReviewState:
    classification = _dump(workflow_state.get("document_classification"))
    extracted_fields = _dump(workflow_state.get("extracted_fields"))
    normalized_fields = _dump(workflow_state.get("normalized_fields"))
    document_input = _dump(workflow_state.get("document_input"))
    artifacts = dict(workflow_state.get("artifacts", {}))
    if document_input:
        artifacts["document_input"] = document_input
    if classification:
        artifacts["document_classification"] = classification
    if workflow_state.get("extraction_metadata"):
        artifacts["extraction_metadata"] = workflow_state.get("extraction_metadata", {})
    if workflow_state.get("source_evidence"):
        artifacts["source_evidence"] = workflow_state.get("source_evidence", {})
    return {
        "input_context": workflow_state["input_context"],
        "document": {
            "document_type": (
                normalized_fields.get("document_type")
                or classification.get("document_type")
                or "food_production_license"
            ),
            "classification": classification,
        },
        "extracted_fields": extracted_fields,
        "normalized_fields": normalized_fields,
        "rule_results": workflow_state.get("rule_results", []),
        "risk_level": workflow_state.get("risk_level"),
        "decision": _decision_from_workflow_state(workflow_state),
        "needs_manual_review": workflow_state.get("needs_manual_review", True),
        "manual_review": workflow_state.get("manual_review"),
        "manual_review_reasons": workflow_state.get("manual_review_reasons", []),
        "summary": workflow_state.get("summary", "食品生产许可证审核结果不完整。"),
        "status": workflow_state.get("status"),
        "artifacts": artifacts,
    }


def _decision_from_workflow_state(workflow_state: dict[str, Any]) -> ReviewDecision:
    status = workflow_state.get("status")
    if status == ReviewStatus.FAILED or str(status) == "FAILED":
        return ReviewDecision.REJECTED
    if workflow_state.get("needs_manual_review", True):
        return ReviewDecision.MANUAL_REVIEW
    return ReviewDecision.REVIEWED


def _dump(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return dict(value)
