from typing import Any, TypedDict

from app.capabilities.tobacco_license.schemas import (
    TobaccoLicenseDocumentClassification,
    TobaccoLicenseDocumentInputResult,
    TobaccoLicenseExtractedFields,
    TobaccoLicenseNormalizedFields,
)
from app.models import ManualReview, ReviewInputContext, RiskLevel, RuleResult


class TobaccoLicenseWorkflowState(TypedDict, total=False):
    input_context: ReviewInputContext
    document_text: str
    llm_structured_fields: dict[str, Any]
    document_input: TobaccoLicenseDocumentInputResult
    document_classification: TobaccoLicenseDocumentClassification
    extracted_fields: TobaccoLicenseExtractedFields
    normalized_fields: TobaccoLicenseNormalizedFields
    extraction_metadata: dict
    source_evidence: dict
    rule_results: list[RuleResult]
    risk_level: RiskLevel
    summary: str
    needs_manual_review: bool
    manual_review_reasons: list[str]
    manual_review: ManualReview
