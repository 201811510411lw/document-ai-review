from app.capabilities.business_license.tools import (
    business_license_classify_document,
    business_license_extract_fields,
    business_license_normalize_fields,
)


def test_business_license_classify_tool_uses_structured_document_type():
    result = business_license_classify_document.invoke(
        {"structured_fields": {"document_type": "business_license"}}
    )

    assert result == {
        "document_type": "business_license",
        "confidence": 1.0,
        "reasons": ["视觉模型返回结构化证照类型"],
    }


def test_business_license_extract_tool_returns_structured_fields_and_metadata():
    result = business_license_extract_fields.invoke(
        {
            "structured_fields": {
                "document_type": "business_license",
                "subject_name": "示例科技有限公司",
                "credit_code": "91310000MA1K000000",
            }
        }
    )

    assert result["fields"] == {
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
    assert result["metadata"] == {
        "structured_extraction": {
            "source": "llm_file_extractor",
            "schema": "BusinessLicenseExtractedFields",
        }
    }


def test_business_license_normalize_tool_cleans_minimum_business_fields():
    result = business_license_normalize_fields.invoke(
        {
            "extracted_fields": {
                "document_type": "营业执照",
                "subject_name": "（ 示例科技有限公司 ）",
                "credit_code": " 91310000 ma1k000000 ",
                "valid_to": "长期有效",
            }
        }
    )

    assert result["document_type"] == "business_license"
    assert result["subject_name"] == "示例科技有限公司"
    assert result["credit_code"] == "91310000MA1K000000"
    assert result["valid_to"] == "长期"
