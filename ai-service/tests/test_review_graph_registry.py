import pytest

from app.models import ReviewInput, ReviewInputContext
from app.workflows.runtime import (
    ReviewGraphDefinition,
    ReviewGraphRegistry,
    ReviewRuntimeEntry,
)


def _context(declared_document_type: str | None) -> ReviewInputContext:
    return ReviewInputContext(
        task_id="review-task-registry",
        input=ReviewInput(
            supplier_name="示例科技有限公司",
            supplier_credit_code="91310000MA1K000000",
            declared_document_type=declared_document_type,
        ),
        use_case_name="",
        use_case_version="",
        ruleset_version="",
    )


def _graph(name: str, *document_types: str) -> ReviewGraphDefinition:
    return ReviewGraphDefinition(
        name=name,
        version="v1",
        ruleset_version=f"{name}-rules-v1",
        supported_document_types=document_types,
        capability_names=(name,),
    )


def test_review_graph_registry_gets_registered_graph_by_name():
    registry = ReviewGraphRegistry()
    graph = _graph("business_license", "business_license")

    registry.register(graph)

    assert registry.get("business_license") == graph
    assert registry.list() == [graph]


def test_review_graph_registry_selects_graph_by_declared_document_type():
    registry = ReviewGraphRegistry()
    business_license = _graph("business_license", "business_license")
    tobacco_license = _graph("tobacco_license", "tobacco_license")
    registry.register(business_license)
    registry.register(tobacco_license)

    assert registry.select(_context("tobacco_license")) == tobacco_license


def test_review_graph_registry_reports_missing_and_ambiguous_routes():
    registry = ReviewGraphRegistry()

    with pytest.raises(LookupError, match="No registered review graph"):
        registry.select(_context("business_license"))

    registry.register(_graph("business_license", "business_license"))
    registry.register(_graph("business_license_v2", "business_license"))

    with pytest.raises(ValueError, match="Multiple registered review graphs"):
        registry.select(_context("business_license"))


def test_review_graph_registry_can_register_invokable_runtime_entry():
    calls = []
    graph = _graph("business_license", "business_license")
    context = _context("business_license")

    def invoke(input_context):
        calls.append(input_context)
        return {"task_id": input_context.task_id, "graph": "business_license"}

    entry = ReviewRuntimeEntry(definition=graph, invoke=invoke)
    registry = ReviewGraphRegistry()
    registry.register_entry(entry)

    selected = registry.select_entry(context)

    assert selected.definition == graph
    assert selected.invoke(context) == {
        "task_id": "review-task-registry",
        "graph": "business_license",
    }
    assert calls == [context]
