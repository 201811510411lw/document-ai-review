from pydantic import BaseModel, Field


class FoodProductionLicenseDocumentClassification(BaseModel):
    document_type: str
    confidence: float | None = None
    reasons: list[str] = Field(default_factory=list)


class FoodProductionLicenseExtractedFields(BaseModel):
    document_type: str | None = None
    producer_name: str | None = None
    credit_code: str | None = None
    license_no: str | None = None
    production_address: str | None = None
    legal_person: str | None = None
    food_categories: list[str] = Field(default_factory=list)
    valid_from: str | None = None
    valid_to: str | None = None
    issue_authority: str | None = None
    issue_date: str | None = None


class FoodProductionLicenseNormalizedFields(BaseModel):
    document_type: str | None = None
    producer_name: str | None = None
    credit_code: str | None = None
    license_no: str | None = None
    production_address: str | None = None
    legal_person: str | None = None
    food_categories: list[str] = Field(default_factory=list)
    valid_from: str | None = None
    valid_to: str | None = None
    issue_authority: str | None = None
    issue_date: str | None = None


class FoodProductionLicenseDocumentInputResult(BaseModel):
    input_type: str
    file_name: str | None = None
    mime_type: str | None = None
    document_format: str | None = None
    source_url: str | None = None


class FoodProductionLicenseCapabilityResult(BaseModel):
    document_input: FoodProductionLicenseDocumentInputResult | None = None
    document_classification: FoodProductionLicenseDocumentClassification | None = None
    extracted_fields: FoodProductionLicenseExtractedFields | None = None
    normalized_fields: FoodProductionLicenseNormalizedFields | None = None
    extraction_metadata: dict = Field(default_factory=dict)
    source_evidence: dict = Field(default_factory=dict)
