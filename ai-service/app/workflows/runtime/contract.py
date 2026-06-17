from datetime import datetime
from enum import StrEnum
from typing import Any, TypedDict
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.models import (
    AuditEvent,
    ManualReview,
    ManualReviewStatus,
    ReviewInputContext,
    ReviewResult,
    ReviewStatus,
    RiskLevel,
    RuleResult,
)


class ReviewDecision(StrEnum):
    REVIEWED = "reviewed"
    MANUAL_REVIEW = "manual_review"
    REJECTED = "rejected"
    FAILED = "failed"


class ReviewState(TypedDict, total=False):
    input_context: ReviewInputContext
    document: dict[str, Any]
    extracted_fields: dict[str, Any]
    normalized_fields: dict[str, Any]
    rule_results: list[RuleResult]
    risk_level: RiskLevel
    decision: ReviewDecision
    needs_manual_review: bool
    manual_review: ManualReview
    manual_review_reasons: list[str]
    summary: str
    status: ReviewStatus
    artifacts: dict[str, Any]
    audit_details: dict[str, Any]


class ReviewGraphDefinition(TypedDict):
    name: str
    version: str
    ruleset_version: str
    supported_document_types: tuple[str, ...]
    capability_names: tuple[str, ...]


class LegacyReviewState(TypedDict, total=False):
    input_context: ReviewInputContext
    decision: ReviewDecision
    skill_result: dict[str, Any]


class ReviewRuntimeContract(TypedDict):
    use_case_name: str
    use_case_version: str
    ruleset_version: str
    document_type: str
    capability_names: tuple[str, ...]


def build_review_result(
    state: ReviewState,
    graph: ReviewGraphDefinition,
    *,
    now: datetime | None = None,
) -> ReviewResult:
    timestamp = now or datetime.now(ZoneInfo(settings.timezone))
    input_context = state["input_context"]
    decision = state.get("decision", ReviewDecision.MANUAL_REVIEW)
    needs_manual_review = state.get(
        "needs_manual_review",
        decision == ReviewDecision.MANUAL_REVIEW,
    )
    document = state.get("document", {})

    document_type = document.get("document_type")
    if document_type == "unknown":
        document_type = None

    return ReviewResult(
        task_id=input_context.task_id,
        use_case_name=graph["name"],
        use_case_version=graph["version"],
        skill_name=graph["name"],
        skill_version=graph["version"],
        ruleset_version=graph["ruleset_version"],
        capability_names=list(graph["capability_names"]),
        document_type=str(
            document_type
            or input_context.input.declared_document_type
            or graph["supported_document_types"][0]
        ),
        status=state.get("status") or _status_for_decision(decision, needs_manual_review),
        risk_level=state.get("risk_level") or RiskLevel.MEDIUM,
        needs_manual_review=needs_manual_review,
        rule_results=state.get("rule_results", []),
        summary=state.get("summary", "审核工作流执行完成。"),
        manual_review=state.get("manual_review")
        or _default_manual_review(state, needs_manual_review),
        audit_events=[
            AuditEvent(
                event_type=f"{graph['name']}.workflow.completed",
                message=f"{graph['name']} 内部工作流执行完成",
                occurred_at=timestamp,
                details=state.get("audit_details", {}),
            )
        ],
        created_at=timestamp,
        updated_at=timestamp,
        skill_result=_skill_result_from_state(state),
    )


def review_result_from_graph_result(
    graph_result: ReviewState,
    contract: ReviewRuntimeContract,
    *,
    now: datetime | None = None,
) -> ReviewResult:
    graph = ReviewGraphDefinition(
        name=contract["use_case_name"],
        version=contract["use_case_version"],
        ruleset_version=contract["ruleset_version"],
        supported_document_types=(contract["document_type"],),
        capability_names=contract["capability_names"],
    )
    return build_review_result(state=graph_result, graph=graph, now=now)


def _status_for_decision(
    decision: ReviewDecision,
    needs_manual_review: bool,
) -> ReviewStatus:
    if decision == ReviewDecision.REJECTED or decision == ReviewDecision.FAILED:
        return ReviewStatus.FAILED
    if needs_manual_review:
        return ReviewStatus.PENDING_MANUAL_REVIEW
    return ReviewStatus.REVIEWED


def _default_manual_review(
    state: ReviewState,
    needs_manual_review: bool,
) -> ManualReview:
    return ManualReview(
        status=(
            ManualReviewStatus.PENDING
            if needs_manual_review
            else ManualReviewStatus.NOT_REQUIRED
        ),
        reasons=state.get("manual_review_reasons", []),
    )


def _skill_result_from_state(state: ReviewState) -> dict[str, Any]:
    artifacts = dict(state.get("artifacts", {}))
    return {
        "document": state.get("document", {}),
        "extracted_fields": state.get("extracted_fields", {}),
        "normalized_fields": state.get("normalized_fields", {}),
        **artifacts,
    }
