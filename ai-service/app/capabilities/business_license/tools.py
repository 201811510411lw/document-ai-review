from typing import Any

from langchain_core.tools import tool

from app.capabilities.business_license.schemas import (
    BusinessLicenseDocumentClassification,
    BusinessLicenseExtractedFields,
    normalize_business_license_fields,
)


@tool
def business_license_classify_document(
    structured_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify whether structured OCR/vision fields describe a business license."""
    fields = structured_fields or {}
    document_type = fields.get("document_type")
    if document_type:
        classification = BusinessLicenseDocumentClassification(
            document_type=document_type,
            confidence=1.0 if document_type == "business_license" else 0.0,
            reasons=["视觉模型返回结构化证照类型"],
        )
    else:
        classification = BusinessLicenseDocumentClassification(
            document_type="unknown",
            confidence=0.0,
            reasons=["未检测到结构化营业执照字段"],
        )
    return classification.model_dump(mode="json")


@tool
def business_license_extract_fields(
    structured_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert structured OCR/vision fields into the business license field schema."""
    fields = structured_fields or {}
    extracted_fields = BusinessLicenseExtractedFields.model_validate(fields)
    metadata: dict[str, Any] = {
        "structured_extraction": {
            "source": "llm_file_extractor",
            "schema": "BusinessLicenseExtractedFields",
        }
    }
    if not fields:
        metadata["structured_extraction"]["status"] = "missing_structured_fields"
    return {
        "fields": extracted_fields.model_dump(mode="json"),
        "metadata": metadata,
    }


@tool
def business_license_normalize_fields(
    extracted_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize extracted business license fields for deterministic rule review."""
    extracted = BusinessLicenseExtractedFields.model_validate(extracted_fields or {})
    return normalize_business_license_fields(extracted).model_dump(mode="json")
