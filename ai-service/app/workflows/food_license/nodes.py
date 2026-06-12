from datetime import date

from app.models import ManualReview, ManualReviewStatus, RiskLevel
from app.rules import RuleContext, RuleExecutor
from app.capabilities.food_license.schemas import (
    FoodLicenseDocumentClassification,
    FoodLicenseDocumentInputResult,
    FoodLicenseExtractedFields,
    FoodLicenseNormalizedFields,
)
from app.capabilities.food_license.rules import build_food_license_rules
from app.tools.license_file_recognition import recognize_license_file
from app.tools.remote_document import RemoteDocumentDownloader
from app.tools.vision_adapter import build_food_license_file_adapter
from app.workflows.food_license.state import FoodLicenseWorkflowState


food_license_remote_downloader = RemoteDocumentDownloader()
food_license_file_adapter = build_food_license_file_adapter()


def load_document(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    input_context = state["input_context"]
    review_input = input_context.input
    recognition_result = recognize_license_file(
        review_input,
        adapter=food_license_file_adapter,
        downloader=food_license_remote_downloader,
    )
    return {
        **state,
        "document_text": recognition_result.document_text,
        "llm_structured_fields": recognition_result.structured_fields,
        "document_input": FoodLicenseDocumentInputResult(
            **{
                key: value
                for key, value in recognition_result.document_input.__dict__.items()
                if key != "source_url"
            }
        ),
        "extraction_metadata": {
            **state.get("extraction_metadata", {}),
            **recognition_result.extraction_metadata,
        },
    }


def classify_document(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    structured_fields = state.get("llm_structured_fields") or {}
    if structured_fields.get("document_type"):
        document_type = structured_fields.get("document_type")
        return {
            **state,
            "document_classification": FoodLicenseDocumentClassification(
                document_type=document_type,
                confidence=1.0 if document_type == "food_license" else 0.0,
                reasons=["大模型文件识别返回结构化证照类型"],
            ),
        }
    return {
        **state,
        "document_classification": FoodLicenseDocumentClassification(
            document_type="unknown",
            confidence=0.0,
            reasons=["大模型文件识别未返回结构化证照类型"],
        ),
    }


def extract_fields(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    structured_fields = state.get("llm_structured_fields") or {}
    if structured_fields:
        extracted_fields = FoodLicenseExtractedFields.model_validate(structured_fields)
        return {
            **state,
            "extracted_fields": extracted_fields,
            "extraction_metadata": {
                **state.get("extraction_metadata", {}),
                "structured_extraction": {
                    "source": "llm_file_extractor",
                    "schema": "FoodLicenseExtractedFields",
                },
            },
        }

    return {
        **state,
        "extracted_fields": FoodLicenseExtractedFields(),
        "extraction_metadata": {
            **state.get("extraction_metadata", {}),
            "structured_extraction": {
                "source": "llm_file_extractor",
                "schema": "FoodLicenseExtractedFields",
                "status": "missing_structured_fields",
            },
        },
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
            "input_context": state["input_context"],
            "current_date": _current_rule_date(),
        },
    )
    rule_execution = RuleExecutor(build_food_license_rules()).run(rule_context)
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
    if state.get("extraction_metadata", {}).get("input_error", {}).get("code") == "UNSUPPORTED_TEXT_DOCUMENT_INPUT":
        reasons.append("食品许可证审核不支持文本输入，请提供 PDF/JPG/JPEG/PNG 文件")
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


def _current_rule_date() -> date:
    return date.today()
