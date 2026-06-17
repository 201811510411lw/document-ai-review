from typing import Any

from app.models import ManualReview, ReviewStatus, RiskLevel, RuleResult


def build_review_graph_trace(
    *,
    graph_name: str,
    graph_version: str,
    ruleset_version: str,
    task_id: str,
    events: list[dict[str, Any]],
    document_type: str,
    status: ReviewStatus | str,
    risk_level: RiskLevel | str,
    needs_manual_review: bool,
    rule_results: list[RuleResult],
    manual_review: ManualReview,
) -> dict[str, Any]:
    return {
        "schema_version": "review-graph-trace-v1",
        "graph_name": graph_name,
        "graph_version": graph_version,
        "ruleset_version": ruleset_version,
        "task_id": task_id,
        "events": events,
        "final": {
            "status": _value(status),
            "risk_level": _value(risk_level),
            "needs_manual_review": needs_manual_review,
            "document_type": document_type,
            "rule_codes": [rule.rule_code for rule in rule_results],
            "manual_review_reasons": list(manual_review.reasons),
        },
    }


def _value(value) -> str:
    return getattr(value, "value", str(value))
