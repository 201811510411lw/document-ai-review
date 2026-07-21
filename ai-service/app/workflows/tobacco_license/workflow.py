from datetime import date
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.capabilities.tobacco_license.schemas import (
    TobaccoLicenseDocumentClassification,
    TobaccoLicenseDocumentInputResult,
    TobaccoLicenseExtractedFields,
    TobaccoLicenseNormalizedFields,
)
from app.capabilities.tobacco_license.tools import (
    tobacco_license_classify_document,
    tobacco_license_extract_fields,
    tobacco_license_normalize_fields,
)
from app.models import (
    ManualReview,
    ManualReviewStatus,
    ReviewInputContext,
    ReviewStatus,
    RiskLevel,
    RuleResult,
)
from app.tools.license_file_recognition import recognize_license_file
from app.tools.vision_adapter import build_tobacco_license_file_adapter


class TobaccoLicenseWorkflowState(TypedDict, total=False):
    input_context: ReviewInputContext
    document_text: str
    vision_structured_fields: dict[str, Any]
    document_input: TobaccoLicenseDocumentInputResult
    document_classification: TobaccoLicenseDocumentClassification
    extracted_fields: TobaccoLicenseExtractedFields
    normalized_fields: TobaccoLicenseNormalizedFields
    extraction_metadata: dict[str, Any]
    source_evidence: dict[str, Any]
    rule_results: list[RuleResult]
    risk_level: RiskLevel
    needs_manual_review: bool
    manual_review_reasons: list[str]
    manual_review: ManualReview
    summary: str
    status: ReviewStatus
    artifacts: dict[str, Any]


tobacco_license_file_adapter = build_tobacco_license_file_adapter()


def build_tobacco_license_graph():
    graph = StateGraph(TobaccoLicenseWorkflowState)
    graph.add_node("load_document", load_document)
    graph.add_node("classify_document", classify_document)
    graph.add_node("extract_fields", extract_fields)
    graph.add_node("normalize_fields", normalize_fields)
    graph.add_node("run_rules", run_rules)
    graph.add_node("summarize_risk", summarize_risk)
    graph.add_node("manual_review", manual_review_node)
    graph.add_node("reviewed", reviewed_node)

    graph.add_edge(START, "load_document")
    graph.add_edge("load_document", "classify_document")
    graph.add_edge("classify_document", "extract_fields")
    graph.add_edge("extract_fields", "normalize_fields")
    graph.add_edge("normalize_fields", "run_rules")
    graph.add_edge("run_rules", "summarize_risk")
    graph.add_conditional_edges(
        "summarize_risk",
        route_after_risk,
        {
            "manual_review": "manual_review",
            "reviewed": "reviewed",
        },
    )
    graph.add_edge("manual_review", END)
    graph.add_edge("reviewed", END)
    return graph.compile()


def load_document(state: TobaccoLicenseWorkflowState) -> TobaccoLicenseWorkflowState:
    input_context = state["input_context"]
    review_input = input_context.input
    recognition_result = recognize_license_file(
        review_input,
        adapter=tobacco_license_file_adapter,
    )
    return {
        **state,
        "document_text": recognition_result.document_text,
        "vision_structured_fields": recognition_result.structured_fields,
        "document_input": TobaccoLicenseDocumentInputResult(
            **recognition_result.document_input.__dict__
        ),
        "extraction_metadata": {
            **state.get("extraction_metadata", {}),
            **recognition_result.extraction_metadata,
        },
        "source_evidence": {
            "supplier_name": review_input.supplier_name,
            "supplier_credit_code": review_input.supplier_credit_code,
            "declared_document_type": review_input.declared_document_type,
            "source": review_input.source,
            "options": review_input.options,
        },
    }


def classify_document(
    state: TobaccoLicenseWorkflowState,
) -> TobaccoLicenseWorkflowState:
    structured_fields = state.get("vision_structured_fields") or {}
    classification = TobaccoLicenseDocumentClassification.model_validate(
        tobacco_license_classify_document.invoke(
            {"structured_fields": structured_fields}
        )
    )
    return {**state, "document_classification": classification}


def extract_fields(state: TobaccoLicenseWorkflowState) -> TobaccoLicenseWorkflowState:
    structured_fields = state.get("vision_structured_fields") or {}
    extraction_result = tobacco_license_extract_fields.invoke(
        {"structured_fields": structured_fields}
    )
    return {
        **state,
        "extracted_fields": TobaccoLicenseExtractedFields.model_validate(
            extraction_result["fields"]
        ),
        "extraction_metadata": {
            **state.get("extraction_metadata", {}),
            **extraction_result.get("metadata", {}),
        },
    }


def normalize_fields(state: TobaccoLicenseWorkflowState) -> TobaccoLicenseWorkflowState:
    extracted = state.get("extracted_fields")
    extracted_payload = extracted.model_dump(mode="json") if extracted else {}
    normalized = TobaccoLicenseNormalizedFields.model_validate(
        tobacco_license_normalize_fields.invoke(
            {"extracted_fields": extracted_payload}
        )
    )
    return {**state, "normalized_fields": normalized}


def run_rules(state: TobaccoLicenseWorkflowState) -> TobaccoLicenseWorkflowState:
    classification = state.get("document_classification")
    fields = state.get("normalized_fields") or TobaccoLicenseNormalizedFields()
    rule_results = _review_rules(classification, fields)
    failed = [rule for rule in rule_results if not rule.passed]
    return {
        **state,
        "rule_results": rule_results,
        "risk_level": _risk_level(failed),
        "needs_manual_review": bool(failed),
        "manual_review_reasons": [_manual_reason(rule) for rule in failed],
    }


def summarize_risk(state: TobaccoLicenseWorkflowState) -> TobaccoLicenseWorkflowState:
    failed = bool(state.get("needs_manual_review", True))
    return {
        **state,
        "summary": (
            "烟草证存在需要人工复核的规则问题"
            if failed
            else "烟草证规则校验通过"
        ),
    }


def manual_review_node(
    state: TobaccoLicenseWorkflowState,
) -> TobaccoLicenseWorkflowState:
    return {
        **state,
        "needs_manual_review": True,
        "manual_review": ManualReview(
            status=ManualReviewStatus.PENDING,
            reasons=list(state.get("manual_review_reasons", [])),
        ),
        "status": ReviewStatus.PENDING_MANUAL_REVIEW,
    }


def reviewed_node(state: TobaccoLicenseWorkflowState) -> TobaccoLicenseWorkflowState:
    return {
        **state,
        "needs_manual_review": False,
        "manual_review": ManualReview(status=ManualReviewStatus.NOT_REQUIRED),
        "status": ReviewStatus.REVIEWED,
    }


def route_after_risk(state: TobaccoLicenseWorkflowState) -> str:
    return "manual_review" if state.get("needs_manual_review", True) else "reviewed"


def run_tobacco_license_workflow(
    input_context: ReviewInputContext,
) -> TobaccoLicenseWorkflowState:
    return _get_tobacco_license_graph().invoke({"input_context": input_context})


def _review_rules(
    classification: TobaccoLicenseDocumentClassification | None,
    fields: TobaccoLicenseNormalizedFields,
) -> list[RuleResult]:
    document_type = classification.document_type if classification else "unknown"
    return [
        RuleResult(
            rule_code="TOBACCO_LICENSE_TYPE_MATCH",
            rule_name="烟草证类型匹配",
            passed=document_type == "tobacco_license",
            risk_level_on_failure=RiskLevel.HIGH,
            message="材料已识别为烟草专卖零售许可证",
            details={"expected": "tobacco_license", "actual": document_type},
        ),
        _required_rule("TOBACCO_LICENSE_SUBJECT_NAME_PRESENT", "企业名称/字号名称存在", "subject_name", fields.subject_name),
        _required_rule("TOBACCO_LICENSE_ADDRESS_PRESENT", "经营场所存在", "business_address", fields.business_address),
        _required_rule("TOBACCO_LICENSE_PERSON_PRESENT", "负责人/经营者存在", "legal_person", fields.legal_person),
        _required_rule("TOBACCO_LICENSE_NO_PRESENT", "许可证号存在", "license_no", fields.license_no),
        _validity_rule(fields.valid_to),
    ]


def _required_rule(code: str, name: str, field: str, value: str | None) -> RuleResult:
    return RuleResult(
        rule_code=code,
        rule_name=name,
        passed=bool(value),
        risk_level_on_failure=RiskLevel.MEDIUM,
        message=name,
        details={"field": field, "actual": value},
    )


def _validity_rule(valid_to: str | None) -> RuleResult:
    if not valid_to:
        return RuleResult(
            rule_code="TOBACCO_LICENSE_VALIDITY_PERIOD",
            rule_name="烟草证有效期",
            passed=True,
            risk_level_on_failure=RiskLevel.MEDIUM,
            message="未识别截止日期，按长期有效处理",
            details={"field": "valid_to", "actual": valid_to, "assumed_long_term": True},
        )
    try:
        days = (date.fromisoformat(valid_to) - date.today()).days
    except ValueError:
        return RuleResult(
            rule_code="TOBACCO_LICENSE_VALIDITY_PERIOD",
            rule_name="烟草证有效期",
            passed=False,
            risk_level_on_failure=RiskLevel.MEDIUM,
            message="有效期无法判断",
            details={"field": "valid_to", "actual": valid_to},
        )
    return RuleResult(
        rule_code="TOBACCO_LICENSE_VALIDITY_PERIOD",
        rule_name="烟草证有效期",
        passed=days > 30,
        risk_level_on_failure=RiskLevel.HIGH if days < 0 else RiskLevel.MEDIUM,
        message="烟草证有效期未过期" if days > 30 else "烟草证已过期或临期",
        details={"field": "valid_to", "actual": valid_to, "days_until_expiry": days},
    )


def _risk_level(failed: list[RuleResult]) -> RiskLevel:
    if any(rule.risk_level_on_failure == RiskLevel.HIGH for rule in failed):
        return RiskLevel.HIGH
    if any(rule.risk_level_on_failure == RiskLevel.MEDIUM for rule in failed):
        return RiskLevel.MEDIUM
    return RiskLevel.NONE


def _manual_reason(rule: RuleResult) -> str:
    if rule.rule_code == "TOBACCO_LICENSE_TYPE_MATCH":
        return "无法确认文件是烟草专卖零售许可证"
    if rule.rule_code == "TOBACCO_LICENSE_VALIDITY_PERIOD":
        return "烟草证有效期需要人工复核"
    return f"{rule.details.get('field')} 缺失"


_tobacco_license_graph: Any = None


def _get_tobacco_license_graph():
    global _tobacco_license_graph
    if _tobacco_license_graph is None:
        _tobacco_license_graph = build_tobacco_license_graph()
    return _tobacco_license_graph
