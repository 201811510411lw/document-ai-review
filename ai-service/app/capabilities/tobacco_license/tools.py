from typing import Any

from langchain_core.tools import tool

from app.capabilities.tobacco_license.schemas import (
    TobaccoLicenseDocumentClassification,
    TobaccoLicenseExtractedFields,
    TobaccoLicenseNormalizedFields,
)


@tool
def tobacco_license_classify_document(
    structured_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify whether structured OCR/vision fields describe a tobacco license."""
    fields = structured_fields or {}
    document_type = fields.get("document_type") or "unknown"
    return TobaccoLicenseDocumentClassification(
        document_type=document_type,
        confidence=1.0 if document_type == "tobacco_license" else 0.0,
        reasons=(
            ["大模型文件识别返回结构化证照类型"]
            if fields
            else ["未返回结构化烟草证字段"]
        ),
    ).model_dump(mode="json")


@tool
def tobacco_license_extract_fields(
    structured_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert structured OCR/vision fields into the tobacco license field schema."""
    fields = structured_fields or {}
    extracted = TobaccoLicenseExtractedFields.model_validate(fields)
    metadata: dict[str, Any] = {
        "structured_extraction": {
            "source": "llm_file_extractor",
            "schema": "TobaccoLicenseExtractedFields",
        }
    }
    if not fields:
        metadata["structured_extraction"]["status"] = "missing_structured_fields"
    return {
        "fields": extracted.model_dump(mode="json"),
        "metadata": metadata,
    }


@tool
def tobacco_license_normalize_fields(
    extracted_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize extracted tobacco license fields for deterministic rule review."""
    extracted = TobaccoLicenseExtractedFields.model_validate(extracted_fields or {})
    return TobaccoLicenseNormalizedFields.model_validate(
        extracted.model_dump(mode="json")
    ).model_dump(mode="json")
