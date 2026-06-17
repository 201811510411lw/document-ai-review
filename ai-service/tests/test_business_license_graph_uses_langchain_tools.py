from app.models import ReviewInput, ReviewInputContext
from app.workflows.business_license import nodes as business_license_nodes
from app.workflows.business_license.nodes import (
    classify_document,
    extract_fields,
    normalize_fields,
)


def test_business_license_field_nodes_use_langchain_tool_contract():
    state = {
        "input_context": ReviewInputContext(
            task_id="review-task-tools",
            input=ReviewInput(
                supplier_name="示例科技有限公司",
                supplier_credit_code="91310000MA1K000000",
                declared_document_type="business_license",
            ),
            use_case_name="business_license",
            use_case_version="v1",
            ruleset_version="business-license-rules-v1",
        ),
        "vision_structured_fields": {
            "document_type": "营业执照",
            "subject_name": "（ 示例科技有限公司 ）",
            "credit_code": " 91310000 ma1k000000 ",
            "valid_to": "长期有效",
        },
        "extraction_metadata": {},
    }

    state = classify_document(state)
    state = extract_fields(state)
    state = normalize_fields(state)

    assert state["document_classification"].document_type == "营业执照"
    assert state["extracted_fields"].subject_name == "（ 示例科技有限公司 ）"
    assert state["extraction_metadata"]["structured_extraction"] == {
        "source": "llm_file_extractor",
        "schema": "BusinessLicenseExtractedFields",
    }
    assert state["normalized_fields"].document_type == "business_license"
    assert state["normalized_fields"].subject_name == "示例科技有限公司"
    assert state["normalized_fields"].credit_code == "91310000MA1K000000"
    assert state["normalized_fields"].valid_to == "长期"


def test_business_license_field_nodes_invoke_langchain_tools(monkeypatch):
    calls = []

    class StubTool:
        def __init__(self, name, result):
            self.name = name
            self.result = result

        def invoke(self, payload):
            calls.append((self.name, payload))
            return self.result

    monkeypatch.setattr(
        business_license_nodes,
        "business_license_classify_document",
        StubTool(
            "classify",
            {
                "document_type": "business_license",
                "confidence": 1.0,
                "reasons": ["stub classification"],
            },
        ),
    )
    monkeypatch.setattr(
        business_license_nodes,
        "business_license_extract_fields",
        StubTool(
            "extract",
            {
                "fields": {
                    "document_type": "business_license",
                    "subject_name": "示例科技有限公司",
                    "credit_code": "91310000MA1K000000",
                },
                "metadata": {
                    "structured_extraction": {
                        "source": "stub_tool",
                        "schema": "BusinessLicenseExtractedFields",
                    }
                },
            },
        ),
    )
    monkeypatch.setattr(
        business_license_nodes,
        "business_license_normalize_fields",
        StubTool(
            "normalize",
            {
                "document_type": "business_license",
                "subject_name": "示例科技有限公司",
                "credit_code": "91310000MA1K000000",
            },
        ),
    )
    state = {
        "input_context": ReviewInputContext(
            task_id="review-task-tool-calls",
            input=ReviewInput(
                supplier_name="示例科技有限公司",
                supplier_credit_code="91310000MA1K000000",
                declared_document_type="business_license",
            ),
            use_case_name="business_license",
            use_case_version="v1",
            ruleset_version="business-license-rules-v1",
        ),
        "vision_structured_fields": {"document_type": "business_license"},
        "extraction_metadata": {},
    }

    state = business_license_nodes.classify_document(state)
    state = business_license_nodes.extract_fields(state)
    state = business_license_nodes.normalize_fields(state)

    assert [call[0] for call in calls] == ["classify", "extract", "normalize"]
    assert calls[0][1] == {"structured_fields": {"document_type": "business_license"}}
    assert calls[1][1] == {"structured_fields": {"document_type": "business_license"}}
    assert calls[2][1] == {
        "extracted_fields": {
            "document_type": "business_license",
            "subject_name": "示例科技有限公司",
            "credit_code": "91310000MA1K000000",
            "business_address": None,
            "legal_person": None,
            "established_date": None,
            "valid_from": None,
            "valid_to": None,
            "issue_authority": None,
            "issue_date": None,
            "source_page": None,
            "ignored_pages": [],
            "subject_name_evidence": None,
            "credit_code_evidence": None,
            "valid_to_evidence": None,
        }
    }
    assert state["document_classification"].reasons == ["stub classification"]
    assert state["extraction_metadata"]["structured_extraction"]["source"] == "stub_tool"
