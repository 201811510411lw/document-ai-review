from pydantic import BaseModel, Field


class BusinessLicenseDocumentClassification(BaseModel):
    document_type: str
    confidence: float | None = None
    reasons: list[str] = Field(default_factory=list)


class BusinessLicenseExtractedFields(BaseModel):
    document_type: str | None = None
    subject_name: str | None = None
    credit_code: str | None = None
    business_address: str | None = None
    legal_person: str | None = None
    established_date: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    issue_authority: str | None = None
    issue_date: str | None = None


class BusinessLicenseNormalizedFields(BusinessLicenseExtractedFields):
    pass


class BusinessLicenseDocumentInputResult(BaseModel):
    input_type: str
    file_name: str | None = None
    mime_type: str | None = None
    document_format: str | None = None
    source_url: str | None = None


class BusinessLicenseCapabilityResult(BaseModel):
    document_input: BusinessLicenseDocumentInputResult | None = None
    document_classification: BusinessLicenseDocumentClassification | None = None
    extracted_fields: BusinessLicenseExtractedFields | None = None
    normalized_fields: BusinessLicenseNormalizedFields | None = None
    extraction_metadata: dict = Field(default_factory=dict)
    source_evidence: dict = Field(default_factory=dict)
