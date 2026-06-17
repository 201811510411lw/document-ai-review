from datetime import datetime, timezone

import pytest

from app.models import ReviewInput, ReviewInputContext, ReviewResult
from app.services import review_service as review_service_module
from app.services.review_service import ReviewService
from app.workflows.runtime import ReviewGraphDefinition, ReviewRuntimeEntry


def _result(input_context: ReviewInputContext) -> ReviewResult:
    now = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    return ReviewResult.model_validate(
        {
            "task_id": input_context.task_id,
            "use_case_name": input_context.use_case_name,
            "use_case_version": input_context.use_case_version,
            "skill_name": input_context.use_case_name,
            "skill_version": input_context.use_case_version,
            "ruleset_version": input_context.ruleset_version,
            "capability_names": [input_context.use_case_name],
            "document_type": input_context.input.declared_document_type,
            "status": "REVIEWED",
            "risk_level": "NONE",
            "needs_manual_review": False,
            "rule_results": [],
            "summary": "stub",
            "manual_review": {"status": "NOT_REQUIRED"},
            "audit_events": [],
            "created_at": now,
            "updated_at": now,
            "skill_result": {},
        }
    )


def test_review_service_prefers_runtime_registry_for_migrated_named_flow(monkeypatch):
    calls = []

    class StubRuntimeRegistry:
        def get_entry(self, name):
            assert name == "business_license"

            def invoke(input_context):
                calls.append(input_context)
                return _result(input_context)

            return ReviewRuntimeEntry(
                definition=ReviewGraphDefinition(
                    name="business_license",
                    version="v1",
                    ruleset_version="business-license-rules-v1",
                    supported_document_types=("business_license",),
                    capability_names=("business_license",),
                ),
                invoke=invoke,
            )

    monkeypatch.setattr(
        review_service_module,
        "review_graph_registry",
        StubRuntimeRegistry(),
    )

    result = ReviewService().review(
        ReviewInput(
            supplier_name="示例科技有限公司",
            supplier_credit_code="91310000MA1K000000",
            declared_document_type="business_license",
        ),
        use_case_name="business_license",
    )

    assert len(calls) == 1
    assert calls[0].use_case_name == "business_license"
    assert result.use_case_name == "business_license"


def test_review_service_does_not_fallback_when_runtime_entry_is_missing(monkeypatch):
    class EmptyRuntimeRegistry:
        def get_entry(self, name):
            raise KeyError(name)

    monkeypatch.setattr(
        review_service_module,
        "review_graph_registry",
        EmptyRuntimeRegistry(),
    )

    with pytest.raises(KeyError):
        ReviewService().review(
            ReviewInput(
                supplier_name="示例食品有限公司",
                supplier_credit_code="91310000MA1K000000",
                declared_document_type="food_license",
            ),
            use_case_name="food_license",
        )
