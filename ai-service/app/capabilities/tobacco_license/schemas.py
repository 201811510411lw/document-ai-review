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
