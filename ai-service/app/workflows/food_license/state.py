from typing import Any, TypedDict

from app.models import ManualReview, ReviewInputContext, RiskLevel, RuleResult
from app.capabilities.food_license.schemas import (
    FoodLicenseDocumentClassification,
    FoodLicenseDocumentInputResult,
    FoodLicenseExtractedFields,
    FoodLicenseNormalizedFields,
)


class FoodLicenseWorkflowState(TypedDict, total=False):
    input_context: ReviewInputContext
    document_text: str
    llm_structured_fields: dict[str, Any]
    document_input: FoodLicenseDocumentInputResult
    document_classification: FoodLicenseDocumentClassification
    extracted_fields: FoodLicenseExtractedFields
    extraction_metadata: dict
    normalized_fields: FoodLicenseNormalizedFields
    rule_results: list[RuleResult]
    risk_level: RiskLevel
    summary: str
    needs_manual_review: bool
    manual_review_reasons: list[str]
    skill_rule_review_metadata: dict[str, Any]
    manual_review: ManualReview
