from typing import TypedDict

from app.models import ManualReview, ReviewInputContext, RiskLevel, RuleResult
from app.rules import RuleExecutionSummary
from app.skills.food_license.models import (
    FoodLicenseDocumentClassification,
    FoodLicenseExtractedFields,
    FoodLicenseNormalizedFields,
)


class FoodLicenseWorkflowState(TypedDict, total=False):
    input_context: ReviewInputContext
    document_text: str
    document_classification: FoodLicenseDocumentClassification
    extracted_fields: FoodLicenseExtractedFields
    normalized_fields: FoodLicenseNormalizedFields
    rule_results: list[RuleResult]
    rule_execution: RuleExecutionSummary
    risk_level: RiskLevel
    summary: str
    needs_manual_review: bool
    manual_review: ManualReview
