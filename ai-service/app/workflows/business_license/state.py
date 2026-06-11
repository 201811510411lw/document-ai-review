from typing import Any, TypedDict

from app.capabilities.business_license.schemas import (
    BusinessLicenseDocumentClassification,
    BusinessLicenseDocumentInputResult,
    BusinessLicenseExtractedFields,
    BusinessLicenseNormalizedFields,
)
from app.models import ManualReview, ReviewInputContext, RiskLevel, RuleResult


class BusinessLicenseWorkflowState(TypedDict, total=False):
    input_context: ReviewInputContext
    document_text: str
    vision_structured_fields: dict[str, Any]
    document_input: BusinessLicenseDocumentInputResult
    document_classification: BusinessLicenseDocumentClassification
    extracted_fields: BusinessLicenseExtractedFields
    normalized_fields: BusinessLicenseNormalizedFields
    extraction_metadata: dict[str, Any]
    source_evidence: dict[str, Any]
    rule_results: list[RuleResult]
    risk_level: RiskLevel
    needs_manual_review: bool
    manual_review_reasons: list[str]
    manual_review: ManualReview
    summary: str
    status: str
