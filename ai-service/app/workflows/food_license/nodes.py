from app.models import ManualReview, ManualReviewStatus, RiskLevel
from app.capabilities.food_license.schemas import (
    FoodLicenseDocumentClassification,
    FoodLicenseDocumentInputResult,
    FoodLicenseExtractedFields,
    FoodLicenseNormalizedFields,
)
from app.tools.license_file_recognition import recognize_license_file
from app.tools.remote_document import RemoteDocumentDownloader
from app.tools.skill_rule_review import (
    build_food_license_skill_rule_review_adapter,
    load_skill_text,
)
from app.tools.vision_adapter import build_food_license_file_adapter
from app.workflows.food_license.state import FoodLicenseWorkflowState


food_license_remote_downloader = RemoteDocumentDownloader()
food_license_file_adapter = build_food_license_file_adapter()
food_license_skill_rule_review_adapter = build_food_license_skill_rule_review_adapter()


def _current_rule_date():
    from datetime import date

    return date.today()


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
            **recognition_result.document_input.__dict__
        ),
        "extraction_metadata": {
            **state.get("extraction_metadata", {}),
            **recognition_result.extraction_metadata,
        },
        "source_evidence": {
            "supplier_name": review_input.supplier_name,
            "supplier_credit_code": review_input.supplier_credit_code,
            "declared_document_type": review_input.declared_document_type,
            "source": review_input.source,
            "options": review_input.options,
        },
    }


def classify_document(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    structured_fields = state.get("llm_structured_fields") or {}
    if structured_fields.get("document_type"):
        document_type = _normalize_document_type(structured_fields.get("document_type"))
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
        valid_from=_normalize_date_text(extracted_fields.valid_from),
        valid_to=_normalize_date_text(extracted_fields.valid_to),
        issue_authority=extracted_fields.issue_authority,
        issue_date=_normalize_date_text(extracted_fields.issue_date),
    )
    return {
        **state,
        "normalized_fields": normalized_fields,
    }


def run_rules(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    input_context = state["input_context"]
    document_classification = state.get("document_classification")
    normalized_fields = state.get("normalized_fields")
    skill_name = "food-license-review"
    review_payload = {
        "task_id": input_context.task_id,
        "declared_document_type": input_context.input.declared_document_type,
        "document_type": (
            document_classification.document_type
            if document_classification is not None
            else None
        ),
        "source_fields": {
            "supplier_name": input_context.input.supplier_name,
            "supplier_credit_code": input_context.input.supplier_credit_code,
            "supplier_address": input_context.input.supplier_address,
        },
        "extracted_fields": (
            normalized_fields.model_dump(mode="json") if normalized_fields else {}
        ),
        "current_date": _current_rule_date().isoformat(),
        "extraction_metadata": state.get("extraction_metadata", {}),
    }
    rules_result = food_license_skill_rule_review_adapter.review(
        skill_name=skill_name,
        skill_text=load_skill_text(skill_name),
        review_payload=review_payload,
    )
    return {
        **state,
        "rule_results": rules_result.get("rule_results", []),
        "risk_level": rules_result.get("risk_level", RiskLevel.MEDIUM),
        "needs_manual_review": rules_result.get("needs_manual_review", True),
        "summary": rules_result.get("summary", "食品许可证 Skill 规则审核完成。"),
        "manual_review_reasons": rules_result.get("manual_review_reasons", []),
        "skill_rule_review_metadata": {
            **dict(rules_result.get("metadata") or {}),
            "skill_name": skill_name,
        },
    }


def summarize_risk(state: FoodLicenseWorkflowState) -> FoodLicenseWorkflowState:
    return {
        **state,
        "risk_level": state.get("risk_level", RiskLevel.MEDIUM),
        "needs_manual_review": state.get("needs_manual_review", True),
        "summary": state.get("summary", "食品许可证 Skill 规则审核完成。"),
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
        reasons.extend(state.get("manual_review_reasons", []))
    elif needs_manual_review:
        reasons.append("Skill 规则结果需要人工复核")

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


def _normalize_document_type(value) -> str:
    text = "" if value is None else str(value).strip()
    if text in {"food_license", "食品经营许可证"}:
        return "food_license"
    return text or "unknown"


def _normalize_date_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "长期" in text:
        return text
    import re

    match = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日?", text)
    if match:
        year, month, day = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return text
