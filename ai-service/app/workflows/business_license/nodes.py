from app.capabilities.business_license.schemas import (
    BusinessLicenseDocumentClassification,
    BusinessLicenseDocumentInputResult,
    BusinessLicenseExtractedFields,
    BusinessLicenseNormalizedFields,
    normalize_business_license_source_fields,
    normalize_business_license_fields,
)
from app.models import ManualReview, ManualReviewStatus, ReviewStatus, RiskLevel
from app.tools import build_business_license_vision_adapter
from app.tools.license_file_recognition import recognize_license_file
from app.tools.remote_document import RemoteDocumentDownloader
from app.tools.skill_rule_review import (
    build_business_license_skill_rule_review_adapter,
    load_skill_text,
)
from app.workflows.business_license.state import BusinessLicenseWorkflowState


business_license_remote_downloader = RemoteDocumentDownloader()
business_license_vision_adapter = build_business_license_vision_adapter()
business_license_skill_rule_review_adapter = (
    build_business_license_skill_rule_review_adapter()
)


def load_document(state: BusinessLicenseWorkflowState) -> BusinessLicenseWorkflowState:
    input_context = state["input_context"]
    review_input = input_context.input
    recognition_result = recognize_license_file(
        review_input,
        adapter=business_license_vision_adapter,
        downloader=business_license_remote_downloader,
        include_legacy_vision_metadata=True,
    )
    return {
        **state,
        "document_text": recognition_result.document_text,
        "vision_structured_fields": recognition_result.structured_fields,
        "document_input": BusinessLicenseDocumentInputResult(
            **recognition_result.document_input.__dict__
        ),
        "extraction_metadata": {
            **state.get("extraction_metadata", {}),
            **recognition_result.extraction_metadata,
        },
        "source_evidence": _source_evidence(review_input),
    }


def classify_document(state: BusinessLicenseWorkflowState) -> BusinessLicenseWorkflowState:
    structured_fields = state.get("vision_structured_fields") or {}
    if structured_fields.get("document_type"):
        document_type = structured_fields.get("document_type")
        return {
            **state,
            "document_classification": BusinessLicenseDocumentClassification(
                document_type=document_type,
                confidence=1.0 if document_type == "business_license" else 0.0,
                reasons=["视觉模型返回结构化证照类型"],
            ),
        }
    if state.get("extraction_metadata", {}).get("llm_file_extractor") is not None:
        return {
            **state,
            "document_classification": BusinessLicenseDocumentClassification(
                document_type="unknown",
                confidence=0.0,
                reasons=["大模型文件识别未返回结构化证照类型"],
            ),
        }
    return {
        **state,
        "document_classification": BusinessLicenseDocumentClassification(
            document_type="unknown",
            confidence=0.0,
            reasons=["未检测到结构化营业执照字段"],
        ),
    }


def extract_fields(state: BusinessLicenseWorkflowState) -> BusinessLicenseWorkflowState:
    structured_fields = state.get("vision_structured_fields") or {}
    if structured_fields:
        extracted_fields = BusinessLicenseExtractedFields.model_validate(structured_fields)
        return {
            **state,
            "extracted_fields": extracted_fields,
            "extraction_metadata": {
                **state.get("extraction_metadata", {}),
                "structured_extraction": {
                    "source": "llm_file_extractor",
                    "schema": "BusinessLicenseExtractedFields",
                },
            },
        }
    return {
        **state,
        "extracted_fields": BusinessLicenseExtractedFields(),
        "extraction_metadata": {
            **state.get("extraction_metadata", {}),
            "structured_extraction": {
                "source": "llm_file_extractor",
                "schema": "BusinessLicenseExtractedFields",
                "status": "missing_structured_fields",
            },
        },
    }


def normalize_fields(state: BusinessLicenseWorkflowState) -> BusinessLicenseWorkflowState:
    extracted = state.get("extracted_fields")
    normalized = normalize_business_license_fields(extracted)
    return {**state, "normalized_fields": normalized}


def run_rules(state: BusinessLicenseWorkflowState) -> BusinessLicenseWorkflowState:
    input_context = state["input_context"]
    classification = state.get("document_classification")
    normalized_fields = state.get("normalized_fields")
    normalized_payload = (
        normalized_fields.model_dump(mode="json") if normalized_fields else {}
    )
    skill_name = "business-license-review"
    review_payload = {
        "task_id": input_context.task_id,
        "declared_document_type": input_context.input.declared_document_type,
        "document_type": normalized_payload.get("document_type")
        or (classification.document_type if classification else None),
        "source_fields": normalize_business_license_source_fields(
            {
                "supplier_name": input_context.input.supplier_name,
                "supplier_credit_code": input_context.input.supplier_credit_code,
                "supplier_address": input_context.input.supplier_address,
            }
        ),
        "extracted_fields": normalized_payload,
        "source_evidence": state.get("source_evidence", {}),
        "extraction_metadata": state.get("extraction_metadata", {}),
    }
    rules_result = business_license_skill_rule_review_adapter.review(
        skill_name=skill_name,
        skill_text=load_skill_text(skill_name),
        review_payload=review_payload,
    )
    return {
        **state,
        "rule_results": rules_result.get("rule_results", []),
        "risk_level": rules_result.get("risk_level", RiskLevel.MEDIUM),
        "needs_manual_review": rules_result.get("needs_manual_review", True),
        "manual_review_reasons": _manual_review_reasons(
            state,
            rules_result.get("manual_review_reasons", []),
        ),
        "skill_rule_review_metadata": {
            **dict(rules_result.get("metadata") or {}),
            "skill_name": skill_name,
            "status_label": rules_result.get("status_label"),
            "risk_level_label": rules_result.get("risk_level_label"),
        },
        "summary": rules_result.get("summary"),
    }


def summarize_risk(state: BusinessLicenseWorkflowState) -> BusinessLicenseWorkflowState:
    risk_level = state.get("risk_level", RiskLevel.MEDIUM)
    needs_manual_review = state.get("needs_manual_review", True)
    if not needs_manual_review:
        summary = "营业执照规则校验通过"
    elif risk_level == RiskLevel.HIGH:
        summary = "营业执照存在高风险规则问题"
    else:
        summary = "营业执照存在需要人工复核的规则问题"
    return {**state, "summary": summary}


def route_review(state: BusinessLicenseWorkflowState) -> BusinessLicenseWorkflowState:
    needs_manual_review = state.get("needs_manual_review", True)
    reasons = list(state.get("manual_review_reasons", []))
    manual_review = ManualReview(
        status=(
            ManualReviewStatus.PENDING
            if needs_manual_review
            else ManualReviewStatus.NOT_REQUIRED
        ),
        reasons=reasons if needs_manual_review else [],
    )
    return {
        **state,
        "manual_review": manual_review,
        "status": (
            ReviewStatus.PENDING_MANUAL_REVIEW
            if needs_manual_review
            else ReviewStatus.REVIEWED
        ),
    }


def _source_evidence(review_input) -> dict:
    return {
        "supplier_name": review_input.supplier_name,
        "supplier_credit_code": review_input.supplier_credit_code,
        "declared_document_type": review_input.declared_document_type,
        "source": review_input.source,
        "options": review_input.options,
    }


def _manual_review_reasons(
    state: BusinessLicenseWorkflowState,
    rule_reasons: list[str],
) -> list[str]:
    reasons = list(rule_reasons)
    if state.get("extraction_metadata", {}).get("input_error", {}).get("code") == "UNSUPPORTED_TEXT_DOCUMENT_INPUT":
        return ["营业执照审核不支持文本输入，请提供 PDF/JPG/JPEG/PNG 文件", *reasons]
    vision_metadata = state.get("extraction_metadata", {}).get("llm_file_extractor", {})
    if vision_metadata.get("error_code") == "VISION_EXTRACTOR_NOT_CONFIGURED":
        return ["视觉模型未配置或未返回文本", *reasons]
    if vision_metadata.get("error_code") == "VISION_EXTRACTOR_MODEL_CALL_FAILED":
        return ["视觉模型调用失败", *reasons]
    return reasons
