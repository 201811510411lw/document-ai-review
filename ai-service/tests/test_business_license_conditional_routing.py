from app.models import ReviewStatus, RiskLevel
from app.workflows.business_license.nodes import (
    manual_review_node,
    reject_node,
    reviewed_node,
)
from app.workflows.business_license.workflow import (
    build_business_license_graph,
    route_after_classification,
    route_after_risk,
)


def test_business_license_graph_has_explicit_conditional_review_routes():
    graph = build_business_license_graph().get_graph()

    for node_name in ["reject", "manual_review", "reviewed"]:
        assert node_name in graph.nodes

    conditional_edges = {
        (edge.source, edge.target)
        for edge in graph.edges
        if edge.conditional
    }

    assert ("classify_document", "reject") in conditional_edges
    assert ("classify_document", "extract_fields") in conditional_edges
    assert ("summarize_risk", "manual_review") in conditional_edges
    assert ("summarize_risk", "reviewed") in conditional_edges
    assert ("summarize_risk", "reject") in conditional_edges


def test_business_license_graph_routing_functions_are_state_driven():
    assert (
        route_after_classification(
            {"document_classification": {"document_type": "business_license"}}
        )
        == "extract_fields"
    )
    assert (
        route_after_classification(
            {"document_classification": {"document_type": "营业执照"}}
        )
        == "extract_fields"
    )
    assert (
        route_after_classification(
            {"document_classification": {"document_type": "unknown"}}
        )
        == "extract_fields"
    )
    assert (
        route_after_classification(
            {"document_classification": {"document_type": "food_license"}}
        )
        == "reject"
    )
    assert route_after_risk({"status": ReviewStatus.FAILED}) == "reject"
    assert route_after_risk({"needs_manual_review": True}) == "manual_review"
    assert route_after_risk({"needs_manual_review": False}) == "reviewed"


def test_business_license_terminal_route_nodes_set_review_status():
    manual = manual_review_node(
        {
            "needs_manual_review": True,
            "manual_review_reasons": ["字段缺失"],
        }
    )
    reviewed = reviewed_node(
        {
            "needs_manual_review": False,
            "manual_review_reasons": ["不应保留"],
        }
    )
    rejected = reject_node(
        {
            "manual_review_reasons": ["无法确认文件是营业执照"],
        }
    )

    assert manual["status"] == ReviewStatus.PENDING_MANUAL_REVIEW
    assert manual["manual_review"].reasons == ["字段缺失"]
    assert reviewed["status"] == ReviewStatus.REVIEWED
    assert reviewed["manual_review"].reasons == []
    assert rejected["status"] == ReviewStatus.FAILED
    assert rejected["risk_level"] == RiskLevel.HIGH
    assert rejected["needs_manual_review"] is False
