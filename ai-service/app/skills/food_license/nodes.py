import re

from app.models import ManualReview, ManualReviewStatus, RiskLevel, RuleResult
from app.skills.food_license.models import (
    FoodLicenseDocumentClassification,
    FoodLicenseExtractedFields,
    FoodLicenseNormalizedFields,
)
from app.skills.food_license.rules.rule_defs import evaluate_food_license_rules
from app.skills.food_license.state import FoodLicenseWorkflowState


def load_document(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    input_context = state["input_context"]
    return {
        **state,
        "document_text": input_context.input.ocr_text.strip(),
    }


def classify_document(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    document_text = state.get("document_text", "")
    has_food_license_marker = (
        "食品经营许可证" in document_text
        or "许可证编号" in document_text
        or re.search(r"\bJY\d{10,}\b", document_text) is not None
    )
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
    document_text = state.get("document_text", "")
    return {
        **state,
        "extracted_fields": FoodLicenseExtractedFields(
            subject_name=_extract_line_value(document_text, ("经营者名称", "名称", "主体名称")),
            credit_code=_extract_line_value(document_text, ("统一社会信用代码", "社会信用代码")),
            license_no=_extract_line_value(document_text, ("许可证编号", "编号")),
            business_address=_extract_line_value(document_text, ("经营场所", "经营地址", "住所")),
            business_items=_extract_business_items(document_text),
            valid_to=_extract_line_value(document_text, ("有效期至", "有效期截止日期", "有效期限至")),
        ),
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
    input_context = state["input_context"]
    classification = state.get("document_classification")
    fields = state.get("normalized_fields") or FoodLicenseNormalizedFields()
    document_type = (
        classification.document_type if classification is not None else "unknown"
    )

    return {
        **state,
        "rule_results": evaluate_food_license_rules(
            document_text=state.get("document_text", ""),
            document_type=document_type,
            fields=fields,
            review_input=input_context.input,
        ),
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
    document_classification = state.get("document_classification")
    unknown_document_type = (
        document_classification is None
        or document_classification.document_type != "food_license"
    )
    needs_manual_review = unknown_document_type or risk_level in {
        RiskLevel.HIGH,
        RiskLevel.MEDIUM,
    }
    reasons = []
    if unknown_document_type:
        reasons.append("文档类型无法识别，需要人工复核")
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


def _extract_line_value(document_text: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        pattern = rf"{re.escape(label)}\s*[:：]\s*([^\n]+)"
        match = re.search(pattern, document_text)
        if match:
            return match.group(1).strip()
    return None


def _extract_business_items(document_text: str) -> list[str]:
    value = _extract_line_value(document_text, ("经营项目", "经营范围"))
    if not value:
        return []
    return [item.strip() for item in re.split(r"[、,，;；]", value) if item.strip()]
