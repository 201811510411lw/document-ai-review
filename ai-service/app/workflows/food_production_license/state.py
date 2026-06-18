from typing import Any, TypedDict

from app.capabilities.food_production_license.schemas import (
    FoodProductionLicenseDocumentClassification,
    FoodProductionLicenseDocumentInputResult,
    FoodProductionLicenseExtractedFields,
    FoodProductionLicenseNormalizedFields,
)
from app.models import ManualReview, ReviewInputContext, RiskLevel, RuleResult


class FoodProductionLicenseWorkflowState(TypedDict, total=False):
    input_context: ReviewInputContext
    document_text: str
    llm_structured_fields: dict[str, Any]
    document_input: FoodProductionLicenseDocumentInputResult
    document_classification: FoodProductionLicenseDocumentClassification
    extracted_fields: FoodProductionLicenseExtractedFields
    extraction_metadata: dict
    source_evidence: dict
    normalized_fields: FoodProductionLicenseNormalizedFields
    rule_results: list[RuleResult]
    risk_level: RiskLevel
    summary: str
    needs_manual_review: bool
    manual_review_reasons: list[str]
    skill_rule_review_metadata: dict[str, Any]
    manual_review: ManualReview
