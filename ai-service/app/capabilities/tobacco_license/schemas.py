import re

from pydantic import BaseModel, Field


class TobaccoLicenseDocumentClassification(BaseModel):
    document_type: str
    confidence: float | None = None
    reasons: list[str] = Field(default_factory=list)


class TobaccoLicenseExtractedFields(BaseModel):
    document_type: str | None = None
    subject_name: str | None = None
    business_address: str | None = None
    legal_person: str | None = None
    license_no: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None


class TobaccoLicenseNormalizedFields(TobaccoLicenseExtractedFields):
    pass


def normalize_tobacco_license_fields(
    extracted: TobaccoLicenseExtractedFields | None,
) -> TobaccoLicenseNormalizedFields:
    if extracted is None:
        return TobaccoLicenseNormalizedFields()
    payload = extracted.model_dump(mode="json")
    return TobaccoLicenseNormalizedFields.model_validate(
        {
            **payload,
            "valid_from": _normalize_date_text(payload.get("valid_from")),
            "valid_to": _normalize_date_text(payload.get("valid_to")),
        }
    )


def _normalize_date_text(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text in {"长期", "永久", "无固定期限", "长期有效"}:
        return "长期"
    match = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日?", text)
    if match:
        year, month, day = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return text


class TobaccoLicenseDocumentInputResult(BaseModel):
    input_type: str
    file_name: str | None = None
    mime_type: str | None = None
    document_format: str | None = None
    source_url: str | None = None


class TobaccoLicenseCapabilityResult(BaseModel):
    document_input: TobaccoLicenseDocumentInputResult | None = None
    document_classification: TobaccoLicenseDocumentClassification | None = None
    extracted_fields: TobaccoLicenseExtractedFields | None = None
    normalized_fields: TobaccoLicenseNormalizedFields | None = None
    extraction_metadata: dict = Field(default_factory=dict)
    source_evidence: dict = Field(default_factory=dict)
