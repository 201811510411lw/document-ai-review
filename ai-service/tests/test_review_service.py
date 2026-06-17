from datetime import datetime, timezone
from uuid import UUID

from app.models import ReviewInput, ReviewInputContext, ReviewResult
from app.services import review_service as review_service_module
from app.services.review_service import ReviewService
from app.workflows.runtime import ReviewGraphDefinition, ReviewRuntimeEntry


def test_review_service_gets_food_license_runtime_entry_and_invokes_it(
    monkeypatch,
):
    calls = []

    class StubRuntimeRegistry:
        def __init__(self) -> None:
            self.requested_names = []

        def get_entry(self, use_case_name: str):
            self.requested_names.append(use_case_name)

            def invoke(input_context: ReviewInputContext) -> ReviewResult:
                calls.append(input_context)
                return _stub_result(input_context)

            return ReviewRuntimeEntry(
                definition=ReviewGraphDefinition(
                    name="food_license",
                    version="v1",
                    ruleset_version="food-license-rules-v1",
                    supported_document_types=("food_license",),
                    capability_names=("food_license",),
                ),
                invoke=invoke,
            )

    registry = StubRuntimeRegistry()
    monkeypatch.setattr(review_service_module, "review_graph_registry", registry)

    result = ReviewService().review_food_license(
        ReviewInput(
            ocr_text="食品经营许可证",
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
        )
    )

    assert registry.requested_names == ["food_license"]
    assert len(calls) == 1
    assert calls[0].use_case_name == "food_license"
    assert calls[0].skill_name == "food_license"
    assert _is_review_task_uuid(calls[0].task_id)
    assert calls[0].input.supplier_credit_code == "91510100MA00000000"
    assert result.use_case_name == "food_license"
    assert result.skill_name == "food_license"


def test_review_service_review_can_call_runtime_entry_by_name(monkeypatch):
    calls = []

    class StubRegistry:
        def __init__(self) -> None:
            self.requested_graph_names = []

        def get_entry(self, graph_name: str):
            self.requested_graph_names.append(graph_name)

            def invoke(input_context: ReviewInputContext) -> ReviewResult:
                calls.append(input_context)
                return _stub_result(input_context)

            return ReviewRuntimeEntry(
                definition=ReviewGraphDefinition(
                    name="qc_document_review",
                    version="v1",
                    ruleset_version="qc-document-rules-v1",
                    supported_document_types=("qc_document_review",),
                    capability_names=("qc_document_review",),
                ),
                invoke=invoke,
            )

    registry = StubRegistry()
    monkeypatch.setattr(review_service_module, "review_graph_registry", registry)

    result = ReviewService().review(
        ReviewInput(
            ocr_text="质检报告文本",
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="qc_document_review",
        ),
        use_case_name="qc_document_review",
    )

    assert registry.requested_graph_names == ["qc_document_review"]
    assert len(calls) == 1
    assert calls[0].use_case_name == "qc_document_review"
    assert _is_review_task_uuid(calls[0].task_id)
    assert result.use_case_name == "qc_document_review"
    assert result.skill_name == "qc_document_review"


def test_review_service_review_can_select_runtime_entry(monkeypatch):
    calls = []

    class StubRegistry:
        def __init__(self) -> None:
            self.select_calls = []

        def select_entry(self, input_context: ReviewInputContext):
            self.select_calls.append(input_context)

            def invoke(runtime_context: ReviewInputContext) -> ReviewResult:
                calls.append(runtime_context)
                return _stub_result(runtime_context)

            return ReviewRuntimeEntry(
                definition=ReviewGraphDefinition(
                    name="qc_document_review",
                    version="v1",
                    ruleset_version="qc-document-rules-v1",
                    supported_document_types=("qc_document_review",),
                    capability_names=("qc_document_review",),
                ),
                invoke=invoke,
            )

    registry = StubRegistry()
    monkeypatch.setattr(review_service_module, "review_graph_registry", registry)

    result = ReviewService().review(
        ReviewInput(
            ocr_text="质检报告文本",
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="qc_document_review",
        )
    )

    assert len(registry.select_calls) == 1
    assert registry.select_calls[0].use_case_name == ""
    assert len(calls) == 1
    assert calls[0].use_case_name == "qc_document_review"
    assert _is_review_task_uuid(calls[0].task_id)
    assert result.use_case_name == "qc_document_review"
    assert result.skill_name == "qc_document_review"


def test_review_service_generates_unique_uuid_task_ids(monkeypatch):
    class StubRuntimeRegistry:
        def get_entry(self, use_case_name: str):
            def invoke(input_context: ReviewInputContext) -> ReviewResult:
                return _stub_result(input_context)

            return ReviewRuntimeEntry(
                definition=ReviewGraphDefinition(
                    name="food_license",
                    version="v1",
                    ruleset_version="food-license-rules-v1",
                    supported_document_types=("food_license",),
                    capability_names=("food_license",),
                ),
                invoke=invoke,
            )

    monkeypatch.setattr(
        review_service_module,
        "review_graph_registry",
        StubRuntimeRegistry(),
    )
    service = ReviewService()
    review_input = ReviewInput(
        ocr_text="食品经营许可证",
        supplier_name="成都示例食品有限公司",
        supplier_credit_code="91510100MA00000000",
    )

    first = service.review_food_license(review_input)
    second = service.review_food_license(review_input)

    assert _is_review_task_uuid(first.task_id)
    assert _is_review_task_uuid(second.task_id)
    assert first.task_id != second.task_id


def _is_review_task_uuid(task_id: str) -> bool:
    prefix = "review-task-"
    if not task_id.startswith(prefix):
        return False
    try:
        UUID(task_id.removeprefix(prefix))
    except ValueError:
        return False
    return True


def _stub_result(input_context: ReviewInputContext) -> ReviewResult:
    now = datetime(2026, 6, 8, 14, 30, tzinfo=timezone.utc)
    return ReviewResult.model_validate(
        {
            "task_id": input_context.task_id,
            "use_case_name": input_context.use_case_name,
            "use_case_version": input_context.use_case_version,
            "skill_name": input_context.use_case_name,
            "skill_version": input_context.use_case_version,
            "ruleset_version": input_context.ruleset_version,
            "document_type": input_context.input.declared_document_type
            or input_context.use_case_name,
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
