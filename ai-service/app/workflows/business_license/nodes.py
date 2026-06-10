from datetime import date

from app.capabilities.business_license.extractor import extract_business_license_fields
from app.capabilities.business_license.rules import evaluate_business_license_rules
from app.capabilities.business_license.schemas import (
    BusinessLicenseDocumentClassification,
    BusinessLicenseDocumentInputResult,
    BusinessLicenseNormalizedFields,
)
from app.models import ManualReview, ManualReviewStatus, ReviewStatus, RiskLevel
from app.tools.remote_document import RemoteDocumentDownloadError, RemoteDocumentDownloader
from app.workflows.business_license.state import BusinessLicenseWorkflowState


business_license_remote_downloader = RemoteDocumentDownloader()


def load_document(state: BusinessLicenseWorkflowState) -> BusinessLicenseWorkflowState:
    input_context = state["input_context"]
    review_input = input_context.input
    ocr_text = (review_input.ocr_text or "").strip()
    if ocr_text:
        return {
            **state,
            "document_text": ocr_text,
            "document_input": BusinessLicenseDocumentInputResult(input_type="ocr_text"),
            "source_evidence": _source_evidence(review_input),
        }

    file_input = review_input.file or review_input.document
    if file_input is not None and (file_input.stub_text or "").strip():
        return {
            **state,
            "document_text": file_input.stub_text.strip(),
            "document_input": BusinessLicenseDocumentInputResult(
                input_type="stub_text",
                file_name=file_input.file_name,
                mime_type=file_input.mime_type,
                document_format=file_input.document_format or file_input.file_type,
                source_url=file_input.file_uri,
            ),
            "source_evidence": _source_evidence(review_input),
        }

    if file_input is not None and file_input.file_uri:
        try:
            remote_document = business_license_remote_downloader.download(
                file_input.file_uri
            )
        except RemoteDocumentDownloadError as error:
            return {
                **state,
                "document_text": "",
                "document_input": BusinessLicenseDocumentInputResult(
                    input_type="remote_error",
                    file_name=file_input.file_name,
                    source_url=file_input.file_uri,
                ),
                "extraction_metadata": {
                    "remote_document_error": {
                        "code": error.code,
                        "source_url": error.source_url,
                        "status_code": error.status_code,
                    }
                },
                "source_evidence": _source_evidence(review_input),
            }
        return {
            **state,
            "document_text": "",
            "document_input": BusinessLicenseDocumentInputResult(
                input_type=remote_document.file_type,
                file_name=file_input.file_name,
                mime_type=remote_document.mime_type,
                document_format=remote_document.file_type,
                source_url=remote_document.source_url,
            ),
            "extraction_metadata": {
                "remote_document": {
                    "status_code": remote_document.status_code,
                    "file_type": remote_document.file_type,
                    "mime_type": remote_document.mime_type,
                    "needs_ocr": True,
                }
            },
            "source_evidence": _source_evidence(review_input),
        }

    return {
        **state,
        "document_text": "",
        "document_input": BusinessLicenseDocumentInputResult(input_type="empty"),
        "source_evidence": _source_evidence(review_input),
    }


def classify_document(state: BusinessLicenseWorkflowState) -> BusinessLicenseWorkflowState:
    document_text = state.get("document_text", "")
    has_marker = "营业执照" in document_text
    return {
        **state,
        "document_classification": BusinessLicenseDocumentClassification(
            document_type="business_license" if has_marker else "unknown",
            confidence=1.0 if has_marker else 0.0,
            reasons=(
                ["OCR 文本包含营业执照特征"]
                if has_marker
                else ["OCR 文本未检测到营业执照特征"]
            ),
        ),
    }


def extract_fields(state: BusinessLicenseWorkflowState) -> BusinessLicenseWorkflowState:
    extracted_fields, metadata = extract_business_license_fields(
        state.get("document_text", "")
    )
    return {
        **state,
        "extracted_fields": extracted_fields,
        "extraction_metadata": {
            **state.get("extraction_metadata", {}),
            **metadata,
        },
    }


def normalize_fields(state: BusinessLicenseWorkflowState) -> BusinessLicenseWorkflowState:
    extracted = state.get("extracted_fields")
    normalized = BusinessLicenseNormalizedFields.model_validate(
        extracted.model_dump() if extracted is not None else {}
    )
    return {**state, "normalized_fields": normalized}


def run_rules(state: BusinessLicenseWorkflowState) -> BusinessLicenseWorkflowState:
    input_context = state["input_context"]
    classification = state.get("document_classification")
    normalized_fields = state.get("normalized_fields")
    rules_result = evaluate_business_license_rules(
        document_type=classification.document_type if classification else None,
        source_subject_name=input_context.input.supplier_name,
        source_credit_code=input_context.input.supplier_credit_code,
        extracted_fields=normalized_fields.model_dump() if normalized_fields else {},
        current_date=date.today(),
    )
    return {
        **state,
        "rule_results": rules_result["rule_results"],
        "risk_level": rules_result["risk_level"],
        "needs_manual_review": rules_result["needs_manual_review"],
        "manual_review_reasons": rules_result["manual_review_reasons"],
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
