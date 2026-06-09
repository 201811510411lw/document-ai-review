from app.models import ManualReview, ManualReviewStatus, RiskLevel
from app.rules import RuleContext, RuleExecutionResult, RuleExecutor
from app.skills.food_license.models import (
    FoodLicenseDocumentClassification,
    FoodLicenseExtractedFields,
    FoodLicenseNormalizedFields,
)
from app.workflows.food_license.state import FoodLicenseWorkflowState


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


class FoodLicenseRuleEngineStubRule:
    code = "FOOD_LICENSE_RULE_ENGINE_STUB"
    name = "food_license 规则执行器接入占位规则"
    risk_level_on_failure = RiskLevel.LOW

    def evaluate(self, context: RuleContext) -> RuleExecutionResult:
        return RuleExecutionResult.passed(
            rule=self,
            message="food_license 已接入通用规则执行器。",
            details={"document_type": context.facts.get("document_type")},
        )


def run_rules(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    document_classification = state.get("document_classification")
    rule_context = RuleContext(
        input_context=state["input_context"],
        facts={
            "document_text": state.get("document_text", ""),
            "document_type": (
                document_classification.document_type
                if document_classification is not None
                else None
            ),
            "extracted_fields": state.get("extracted_fields"),
            "normalized_fields": state.get("normalized_fields"),
        },
    )
    rule_execution = RuleExecutor([FoodLicenseRuleEngineStubRule()]).run(rule_context)
    return {
        **state,
        "rule_execution": rule_execution,
        "rule_results": rule_execution.to_rule_results(),
    }


def summarize_risk(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    rule_execution = state.get("rule_execution")
    if rule_execution is not None:
        return {
            **state,
            "risk_level": rule_execution.risk_level,
            "needs_manual_review": rule_execution.needs_manual_review,
            "summary": _summarize_rule_execution(
                rule_execution.risk_level,
                rule_execution.needs_manual_review,
            ),
        }

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
    document_classification = state.get("document_classification")
    unknown_document_type = (
        document_classification is None
        or document_classification.document_type != "food_license"
    )
    rule_execution_needs_manual_review = state.get("needs_manual_review", False)
    needs_manual_review = (
        rule_execution_needs_manual_review
        or unknown_document_type
        or risk_level in {RiskLevel.HIGH, RiskLevel.MEDIUM}
    )
    reasons = []
    if unknown_document_type:
        reasons.append("文档类型无法识别，需要人工复核")
    elif rule_execution_needs_manual_review:
        reasons.append("规则执行异常或不完整，需要人工复核")
    elif needs_manual_review:
        reasons.append("确定性规则结果需要人工复核")

    manual_review = ManualReview(
        status=(
            ManualReviewStatus.PENDING
            if needs_manual_review
            else ManualReviewStatus.NOT_REQUIRED
        ),
        reasons=reasons,
    )
    return {
        **state,
        "needs_manual_review": needs_manual_review,
        "manual_review": manual_review,
    }


def _summarize_rule_execution(
    risk_level: RiskLevel,
    needs_manual_review: bool,
) -> str:
    if needs_manual_review:
        return "规则执行需要人工复核。"
    if risk_level == RiskLevel.NONE:
        return "未发现确定性规则风险。"
    return "发现确定性规则风险。"
