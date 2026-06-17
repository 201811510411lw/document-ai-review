from app.capabilities.tobacco_license.tools import (
    tobacco_license_classify_document,
    tobacco_license_extract_fields,
    tobacco_license_normalize_fields,
)
from app.models import (
    ManualReview,
    ManualReviewStatus,
    ReviewInput,
    ReviewInputContext,
    ReviewStatus,
    RiskLevel,
)
from app.use_cases.tobacco_license import use_case as tobacco_license_use_case_module
from app.use_cases.tobacco_license.use_case import TobaccoLicenseUseCase
from app.workflows.tobacco_license.workflow import build_tobacco_license_graph


def test_tobacco_license_langchain_tools_cover_classify_extract_normalize():
    classification = tobacco_license_classify_document.invoke(
        {"structured_fields": {"document_type": "tobacco_license"}}
    )
    extracted = tobacco_license_extract_fields.invoke(
        {
            "structured_fields": {
                "document_type": "tobacco_license",
                "subject_name": "成都示例烟草商行",
                "license_no": "烟专零售许第1号",
            }
        }
    )
    normalized = tobacco_license_normalize_fields.invoke(
        {"extracted_fields": extracted["fields"]}
    )

    assert classification["document_type"] == "tobacco_license"
    assert classification["confidence"] == 1.0
    assert extracted["fields"]["subject_name"] == "成都示例烟草商行"
    assert extracted["metadata"]["structured_extraction"]["schema"] == "TobaccoLicenseExtractedFields"
    assert normalized["license_no"] == "烟专零售许第1号"


def test_tobacco_license_workflow_is_standard_state_graph():
    graph = build_tobacco_license_graph().get_graph()

    for node_name in [
        "load_document",
        "classify_document",
        "extract_fields",
        "normalize_fields",
        "run_rules",
        "summarize_risk",
        "manual_review",
        "reviewed",
    ]:
        assert node_name in graph.nodes

    conditional_edges = {
        (edge.source, edge.target)
        for edge in graph.edges
        if edge.conditional
    }
    assert ("summarize_risk", "manual_review") in conditional_edges
    assert ("summarize_risk", "reviewed") in conditional_edges


def test_tobacco_license_use_case_is_thin_entry_over_runtime_contract(monkeypatch):
    def stub_workflow(input_context):
        return {
            "input_context": input_context,
            "document": {"document_type": "tobacco_license"},
            "extracted_fields": {
                "document_type": "tobacco_license",
                "subject_name": "成都示例烟草商行",
            },
            "normalized_fields": {
                "document_type": "tobacco_license",
                "subject_name": "成都示例烟草商行",
            },
            "risk_level": RiskLevel.NONE,
            "needs_manual_review": False,
            "manual_review": ManualReview(status=ManualReviewStatus.NOT_REQUIRED),
            "summary": "烟草证规则校验通过",
            "status": ReviewStatus.REVIEWED,
            "artifacts": {"document_input": {"file_name": "tobacco-license.pdf"}},
        }

    monkeypatch.setattr(
        tobacco_license_use_case_module,
        "run_tobacco_license_workflow",
        stub_workflow,
    )
    assert not hasattr(
        tobacco_license_use_case_module,
        "build_tobacco_license_capability_result",
    )
    input_context = ReviewInputContext(
        task_id="review-task-tobacco-thin-entry",
        input=ReviewInput(
            supplier_name="成都示例烟草商行",
            supplier_credit_code="91510100MA0000000X",
            declared_document_type="tobacco_license",
        ),
        use_case_name="tobacco_license",
        use_case_version="v1",
        ruleset_version="tobacco-license-rules-v1",
    )

    result = TobaccoLicenseUseCase().review(input_context)

    assert result.use_case_name == "tobacco_license"
    assert result.capability_names == ["tobacco_license"]
    assert result.document_type == "tobacco_license"
    assert result.status == ReviewStatus.REVIEWED
    assert result.skill_result["document_input"]["file_name"] == "tobacco-license.pdf"
