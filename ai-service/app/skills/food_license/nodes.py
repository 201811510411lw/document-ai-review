from app.models import ManualReview, ManualReviewStatus, RiskLevel
from app.skills.food_license.models import (
    FoodLicenseDocumentClassification,
    FoodLicenseExtractedFields,
    FoodLicenseNormalizedFields,
)
from app.skills.food_license.state import FoodLicenseWorkflowState


def load_document(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    input_context = state["input_context"]
    return {
        **state,
        "document_text": input_context.input.ocr_text.strip(),
    }


def classify_document(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    document_text = state.get("document_text", "")
    has_food_license_marker = "食品经营许可证" in document_text or "食品" in document_text
    classification = FoodLicenseDocumentClassification(
        document_type="food_license" if has_food_license_marker else "unknown",
        confidence=1.0 if has_food_license_marker else 0.0,
        reasons=(
            ["OCR 文本包含食品经营许可证特征"]
            if has_food_license_marker
            else ["OCR 文本未检测到食品经营许可证特征"]
        ),
    )
    return {
        **state,
        "document_classification": classification,
    }


def extract_fields(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    return {
        **state,
        "extracted_fields": FoodLicenseExtractedFields(),
    }


def normalize_fields(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    extracted_fields = state.get("extracted_fields") or FoodLicenseExtractedFields()
    normalized_fields = FoodLicenseNormalizedFields(
        subject_name=extracted_fields.subject_name,
        credit_code=extracted_fields.credit_code,
        license_no=extracted_fields.license_no,
        business_address=extracted_fields.business_address,
        legal_person=extracted_fields.legal_person,
        business_items=list(extracted_fields.business_items),
        valid_from=extracted_fields.valid_from,
        valid_to=extracted_fields.valid_to,
        issue_authority=extracted_fields.issue_authority,
        issue_date=extracted_fields.issue_date,
    )
    return {
        **state,
        "normalized_fields": normalized_fields,
    }


def run_rules(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    return {
        **state,
        "rule_results": [],
    }


def summarize_risk(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    rule_results = state.get("rule_results", [])
    failed_risks = [
        rule_result.risk_level_on_failure
        for rule_result in rule_results
        if not rule_result.passed
    ]

    if RiskLevel.HIGH in failed_risks:
        risk_level = RiskLevel.HIGH
    elif RiskLevel.MEDIUM in failed_risks:
        risk_level = RiskLevel.MEDIUM
    elif RiskLevel.LOW in failed_risks:
        risk_level = RiskLevel.LOW
    else:
        risk_level = RiskLevel.NONE

    return {
        **state,
        "risk_level": risk_level,
        "summary": "未发现确定性规则风险。" if risk_level == RiskLevel.NONE else "发现确定性规则风险。",
    }


def route_review(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    risk_level = state.get("risk_level", RiskLevel.NONE)
    needs_manual_review = risk_level in {RiskLevel.HIGH, RiskLevel.MEDIUM}
    manual_review = ManualReview(
        status=(
            ManualReviewStatus.PENDING
            if needs_manual_review
            else ManualReviewStatus.NOT_REQUIRED
        ),
        reasons=[] if not needs_manual_review else ["确定性规则结果需要人工复核"],
    )
    return {
        **state,
        "needs_manual_review": needs_manual_review,
        "manual_review": manual_review,
    }
