import json

from app.models import (
    ManualReview,
    ManualReviewStatus,
    ReviewStatus,
    RiskLevel,
    RuleResult,
)
from app.workflows.runtime.trace import build_review_graph_trace


def test_review_graph_trace_is_json_serializable_stable_summary():
    trace = build_review_graph_trace(
        graph_name="business_license",
        graph_version="v1",
        ruleset_version="business-license-rules-v1",
        task_id="review-task-trace",
        events=[
            {
                "step": "classify_document",
                "kind": "route",
                "route": "extract_fields",
            }
        ],
        document_type="business_license",
        status=ReviewStatus.REVIEWED,
        risk_level=RiskLevel.NONE,
        needs_manual_review=False,
        rule_results=[
            RuleResult(
                rule_code="BUSINESS_LICENSE_TYPE_MATCH",
                rule_name="营业执照类型匹配",
                passed=True,
                risk_level_on_failure=RiskLevel.HIGH,
                message="材料已识别为营业执照",
            )
        ],
        manual_review=ManualReview(status=ManualReviewStatus.NOT_REQUIRED),
    )

    encoded = json.dumps(trace, ensure_ascii=False)
    decoded = json.loads(encoded)

    assert decoded == {
        "schema_version": "review-graph-trace-v1",
        "graph_name": "business_license",
        "graph_version": "v1",
        "ruleset_version": "business-license-rules-v1",
        "task_id": "review-task-trace",
        "events": [
            {
                "step": "classify_document",
                "kind": "route",
                "route": "extract_fields",
            }
        ],
        "final": {
            "status": "REVIEWED",
            "risk_level": "NONE",
            "needs_manual_review": False,
            "document_type": "business_license",
            "rule_codes": ["BUSINESS_LICENSE_TYPE_MATCH"],
            "manual_review_reasons": [],
        },
    }
