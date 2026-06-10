from pydantic import BaseModel, Field


class FoodLicenseDocumentClassification(BaseModel):
    document_type: str
    confidence: float | None = None
    reasons: list[str] = Field(default_factory=list)


class FoodLicenseExtractedFields(BaseModel):
    subject_name: str | None = None
    credit_code: str | None = None
    license_no: str | None = None
    business_address: str | None = None
    legal_person: str | None = None
    business_items: list[str] = Field(default_factory=list)
    valid_from: str | None = None
    valid_to: str | None = None
    issue_authority: str | None = None
    issue_date: str | None = None


class FoodLicenseNormalizedFields(BaseModel):
    subject_name: str | None = None
    credit_code: str | None = None
    license_no: str | None = None
    business_address: str | None = None
    legal_person: str | None = None
    business_items: list[str] = Field(default_factory=list)
    valid_from: str | None = None
    valid_to: str | None = None
    issue_authority: str | None = None
    issue_date: str | None = None


class FoodLicenseDocumentInputResult(BaseModel):
    input_type: str
    file_name: str | None = None
    mime_type: str | None = None
    document_format: str | None = None


class FoodLicenseCapabilityResult(BaseModel):
    document_input: FoodLicenseDocumentInputResult | None = None
    document_classification: FoodLicenseDocumentClassification | None = None
    extracted_fields: FoodLicenseExtractedFields | None = None
    normalized_fields: FoodLicenseNormalizedFields | None = None
    extraction_metadata: dict = Field(default_factory=dict)
