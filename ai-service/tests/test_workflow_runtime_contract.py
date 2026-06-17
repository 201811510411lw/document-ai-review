from datetime import datetime
from zoneinfo import ZoneInfo

from app.models import (
    ManualReview,
    ManualReviewStatus,
    ReviewInput,
    ReviewInputContext,
    ReviewStatus,
    RiskLevel,
    RuleResult,
)
from app.workflows.runtime import (
    ReviewDecision,
    ReviewGraphDefinition,
    ReviewState,
    build_review_result,
)


def test_review_state_contract_contains_graph_runtime_fields():
    review_input = ReviewInput(
        supplier_name="成都样例商贸有限公司",
        supplier_credit_code="91510100MA0000000X",
        declared_document_type="business_license",
    )
    input_context = ReviewInputContext(
        task_id="review-task-1",
        input=review_input,
        use_case_name="business_license",
        use_case_version="v1",
        ruleset_version="business-license-rules-v1",
    )

    state: ReviewState = {
        "input_context": input_context,
        "document": {"document_type": "business_license"},
        "extracted_fields": {"subject_name": "成都样例商贸有限公司"},
        "normalized_fields": {"subject_name": "成都样例商贸有限公司"},
        "rule_results": [],
        "risk_level": RiskLevel.NONE,
        "decision": ReviewDecision.REVIEWED,
        "manual_review": ManualReview(status=ManualReviewStatus.NOT_REQUIRED),
        "artifacts": {"normalized_fields": {"subject_name": "成都样例商贸有限公司"}},
    }

    assert state["document"]["document_type"] == "business_license"
    assert state["decision"] == ReviewDecision.REVIEWED
    assert state["manual_review"].status == ManualReviewStatus.NOT_REQUIRED


def test_review_state_projects_to_review_result_contract():
    now = datetime(2026, 6, 16, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    review_input = ReviewInput(
        supplier_name="成都样例商贸有限公司",
        supplier_credit_code="91510100MA0000000X",
        declared_document_type="business_license",
    )
    input_context = ReviewInputContext(
        task_id="review-task-2",
        input=review_input,
        use_case_name="business_license",
        use_case_version="v1",
        ruleset_version="business-license-rules-v1",
    )
    graph = ReviewGraphDefinition(
        name="business_license",
        version="v1",
        ruleset_version="business-license-rules-v1",
        supported_document_types=("business_license",),
        capability_names=("business_license",),
    )
    rule = RuleResult(
        rule_code="BUSINESS_LICENSE_TYPE_MATCH",
        rule_name="营业执照类型匹配",
        passed=True,
        risk_level_on_failure=RiskLevel.HIGH,
        message="材料已识别为营业执照",
    )
    state: ReviewState = {
        "input_context": input_context,
        "document": {"document_type": "business_license"},
        "extracted_fields": {"subject_name": "成都样例商贸有限公司"},
        "normalized_fields": {"subject_name": "成都样例商贸有限公司"},
        "rule_results": [rule],
        "risk_level": RiskLevel.NONE,
        "decision": ReviewDecision.REVIEWED,
        "manual_review": ManualReview(status=ManualReviewStatus.NOT_REQUIRED),
        "summary": "营业执照规则校验通过",
        "artifacts": {
            "document_input": {"source_url": "https://example.test/license.pdf"},
            "normalized_fields": {"subject_name": "成都样例商贸有限公司"},
        },
    }

    result = build_review_result(state=state, graph=graph, now=now)

    assert result.task_id == "review-task-2"
    assert result.use_case_name == "business_license"
    assert result.use_case_version == "v1"
    assert result.ruleset_version == "business-license-rules-v1"
    assert result.capability_names == ["business_license"]
    assert result.document_type == "business_license"
    assert result.status == ReviewStatus.REVIEWED
    assert result.risk_level == RiskLevel.NONE
    assert result.needs_manual_review is False
    assert result.rule_results == [rule]
    assert result.manual_review.status == ManualReviewStatus.NOT_REQUIRED
    assert result.created_at == now
    assert result.skill_result["normalized_fields"]["subject_name"] == "成都样例商贸有限公司"
