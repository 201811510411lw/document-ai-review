from langgraph.graph import END, START, StateGraph

from app.models import ReviewInputContext
from app.workflows.business_license.nodes import (
    classify_document,
    extract_fields,
    load_document,
    manual_review_node,
    normalize_fields,
    reject_node,
    reviewed_node,
    run_rules,
    summarize_risk,
)
from app.workflows.business_license.state import BusinessLicenseWorkflowState


def route_after_classification(state: BusinessLicenseWorkflowState) -> str:
    classification = state.get("document_classification")
    if isinstance(classification, dict):
        document_type = classification.get("document_type")
    else:
        document_type = getattr(classification, "document_type", None)
    if document_type in {"business_license", "营业执照", "unknown", None, ""}:
        return "extract_fields"
    return "reject"


def route_after_risk(state: BusinessLicenseWorkflowState) -> str:
    if str(state.get("status")) == "FAILED":
        return "reject"
    if state.get("needs_manual_review", True):
        return "manual_review"
    return "reviewed"


def build_business_license_graph():
    graph = StateGraph(BusinessLicenseWorkflowState)
    graph.add_node("load_document", load_document)
    graph.add_node("classify_document", classify_document)
    graph.add_node("extract_fields", extract_fields)
    graph.add_node("normalize_fields", normalize_fields)
    graph.add_node("run_rules", run_rules)
    graph.add_node("summarize_risk", summarize_risk)
    graph.add_node("reject", reject_node)
    graph.add_node("manual_review", manual_review_node)
    graph.add_node("reviewed", reviewed_node)

    graph.add_edge(START, "load_document")
    graph.add_edge("load_document", "classify_document")
    graph.add_conditional_edges(
        "classify_document",
        route_after_classification,
        {
            "extract_fields": "extract_fields",
            "reject": "reject",
        },
    )
    graph.add_edge("extract_fields", "normalize_fields")
    graph.add_edge("normalize_fields", "run_rules")
    graph.add_edge("run_rules", "summarize_risk")
    graph.add_conditional_edges(
        "summarize_risk",
        route_after_risk,
        {
            "manual_review": "manual_review",
            "reviewed": "reviewed",
            "reject": "reject",
        },
    )
    graph.add_edge("reject", END)
    graph.add_edge("manual_review", END)
    graph.add_edge("reviewed", END)
    return graph.compile()


business_license_graph = build_business_license_graph()


def run_business_license_workflow(
    input_context: ReviewInputContext,
) -> BusinessLicenseWorkflowState:
    return business_license_graph.invoke({"input_context": input_context})
