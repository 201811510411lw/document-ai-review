from langgraph.graph import END, START, StateGraph

from app.models import ReviewInputContext
from app.workflows.food_production_license.nodes import (
    classify_document,
    extract_fields,
    load_document,
    normalize_fields,
    route_review,
    run_rules,
    summarize_risk,
)
from app.workflows.food_production_license.state import FoodProductionLicenseWorkflowState


def build_food_production_license_graph():
    graph = StateGraph(FoodProductionLicenseWorkflowState)
    graph.add_node("load_document", load_document)
    graph.add_node("classify_document", classify_document)
    graph.add_node("extract_fields", extract_fields)
    graph.add_node("normalize_fields", normalize_fields)
    graph.add_node("run_rules", run_rules)
    graph.add_node("summarize_risk", summarize_risk)
    graph.add_node("route_review", route_review)

    graph.add_edge(START, "load_document")
    graph.add_edge("load_document", "classify_document")
    graph.add_edge("classify_document", "extract_fields")
    graph.add_edge("extract_fields", "normalize_fields")
    graph.add_edge("normalize_fields", "run_rules")
    graph.add_edge("run_rules", "summarize_risk")
    graph.add_edge("summarize_risk", "route_review")
    graph.add_edge("route_review", END)
    return graph.compile()


food_production_license_graph = build_food_production_license_graph()


def run_food_production_license_workflow(
    input_context: ReviewInputContext,
) -> FoodProductionLicenseWorkflowState:
    return food_production_license_graph.invoke({"input_context": input_context})
