from datetime import date
from pathlib import Path

from app.capabilities.business_license.extractor import extract_business_license_fields
from app.capabilities.business_license.rules import evaluate_business_license_rules
from app.capabilities.business_license.schemas import (
    BusinessLicenseDocumentClassification,
    BusinessLicenseDocumentInputResult,
    BusinessLicenseNormalizedFields,
)
from app.models import ManualReview, ManualReviewStatus, ReviewStatus, RiskLevel
from app.tools import build_business_license_vision_adapter
from app.tools.document_constraints import (
    enforce_file_size_limit,
    enforce_image_dimension_limit,
)
from app.tools.document_loader import LocalPdfDocumentLoader
from app.tools.remote_document import RemoteDocumentDownloadError, RemoteDocumentDownloader
from app.tools.vision_adapter import VisionInput
from app.workflows.business_license.state import BusinessLicenseWorkflowState


business_license_remote_downloader = RemoteDocumentDownloader()
business_license_vision_adapter = build_business_license_vision_adapter()
business_license_pdf_document_loader = LocalPdfDocumentLoader()


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

    if file_input is not None and _is_local_image_input(file_input):
        vision_input = _local_image_vision_input(file_input)
        vision_result = business_license_vision_adapter.extract_text(vision_input)
        metadata = vision_result.get("metadata", {})
        return {
            **state,
            "document_text": (vision_result.get("text") or "").strip(),
            "vision_structured_fields": vision_result.get("structured_fields") or {},
            "document_input": BusinessLicenseDocumentInputResult(
                input_type="image",
                file_name=file_input.file_name,
                mime_type=file_input.mime_type,
                document_format=file_input.document_format or file_input.file_type,
                source_url=file_input.file_uri,
            ),
            "extraction_metadata": {
                **state.get("extraction_metadata", {}),
                "vision_extractor": metadata,
            },
            "source_evidence": _source_evidence(review_input),
        }

    if file_input is not None and _is_local_pdf_input(file_input):
        loaded_document = business_license_pdf_document_loader.load(file_input)
        metadata = loaded_document.get("metadata", {})
        document_text = (loaded_document.get("text") or "").strip()
        extraction_metadata = {
            **state.get("extraction_metadata", {}),
            "pdf_loader": _pdf_loader_metadata(metadata),
        }
        if not document_text and metadata.get("needs_ocr"):
            vision_result = business_license_vision_adapter.extract_text(
                _local_pdf_vision_input(file_input)
            )
            document_text = (vision_result.get("text") or "").strip()
            extraction_metadata["vision_extractor"] = vision_result.get("metadata", {})
        return {
            **state,
            "document_text": document_text,
            "vision_structured_fields": (
                vision_result.get("structured_fields") or {}
                if "vision_result" in locals()
                else {}
            ),
            "document_input": BusinessLicenseDocumentInputResult(
                input_type="pdf",
                file_name=metadata.get("file_name"),
                mime_type=metadata.get("mime_type"),
                document_format=metadata.get("document_format"),
                source_url=file_input.file_uri,
            ),
            "extraction_metadata": extraction_metadata,
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
        if remote_document.file_type in {"jpg", "jpeg", "png"}:
            enforce_file_size_limit(len(remote_document.content))
            enforce_image_dimension_limit(remote_document.content)
            vision_result = business_license_vision_adapter.extract_text(
                VisionInput(
                    content=remote_document.content,
                    mime_type=remote_document.mime_type,
                    file_name=file_input.file_name,
                    source_url=remote_document.source_url,
                )
            )
            return {
                **state,
                "document_text": (vision_result.get("text") or "").strip(),
                "vision_structured_fields": vision_result.get("structured_fields") or {},
                "document_input": BusinessLicenseDocumentInputResult(
                    input_type="image",
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
                        "needs_vision": True,
                    },
                    "vision_extractor": vision_result.get("metadata", {}),
                },
                "source_evidence": _source_evidence(review_input),
            }
        if remote_document.file_type == "pdf":
            loaded_document = business_license_pdf_document_loader.load_bytes(
                remote_document.content,
                file_name=file_input.file_name,
                mime_type=remote_document.mime_type,
                document_format=remote_document.file_type,
            )
            metadata = loaded_document.get("metadata", {})
            document_text = (loaded_document.get("text") or "").strip()
            extraction_metadata = {
                "remote_document": {
                    "status_code": remote_document.status_code,
                    "file_type": remote_document.file_type,
                    "mime_type": remote_document.mime_type,
                },
                "pdf_loader": _pdf_loader_metadata(metadata),
            }
            if not document_text and metadata.get("needs_ocr"):
                vision_result = business_license_vision_adapter.extract_text(
                    VisionInput(
                        content=remote_document.content,
                        mime_type=remote_document.mime_type,
                        file_name=file_input.file_name,
                        source_url=remote_document.source_url,
                    )
                )
                document_text = (vision_result.get("text") or "").strip()
                extraction_metadata["vision_extractor"] = vision_result.get("metadata", {})
            return {
                **state,
                "document_text": document_text,
                "vision_structured_fields": (
                    vision_result.get("structured_fields") or {}
                    if "vision_result" in locals()
                    else {}
                ),
                "document_input": BusinessLicenseDocumentInputResult(
                    input_type="pdf",
                    file_name=file_input.file_name,
                    mime_type=remote_document.mime_type,
                    document_format=remote_document.file_type,
                    source_url=remote_document.source_url,
                ),
                "extraction_metadata": extraction_metadata,
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
    structured_fields = state.get("vision_structured_fields") or {}
    if structured_fields:
        from app.capabilities.business_license.schemas import BusinessLicenseExtractedFields

        extracted_fields = BusinessLicenseExtractedFields.model_validate(structured_fields)
        return {
            **state,
            "extracted_fields": extracted_fields,
            "extraction_metadata": {
                **state.get("extraction_metadata", {}),
                "structured_extraction": {
                    "source": "vision_adapter",
                    "schema": "BusinessLicenseExtractedFields",
                },
            },
        }
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
        "manual_review_reasons": _manual_review_reasons(
            state,
            rules_result["manual_review_reasons"],
        ),
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
    vision_metadata = state.get("extraction_metadata", {}).get("vision_extractor", {})
    if vision_metadata.get("error_code") == "VISION_EXTRACTOR_NOT_CONFIGURED":
        return ["视觉模型未配置或未返回文本", *reasons]
    if vision_metadata.get("error_code") == "VISION_EXTRACTOR_MODEL_CALL_FAILED":
        return ["视觉模型调用失败", *reasons]
    return reasons


def _is_local_image_input(file_input) -> bool:
    local_path = getattr(file_input, "local_path", None) or getattr(
        file_input,
        "file_path",
        None,
    )
    mime_type = getattr(file_input, "mime_type", None) or ""
    return bool(local_path) and mime_type.startswith("image/")


def _local_image_vision_input(file_input) -> VisionInput:
    local_path = getattr(file_input, "local_path", None) or getattr(
        file_input,
        "file_path",
        None,
    )
    path = Path(local_path).expanduser().resolve(strict=True)
    enforce_file_size_limit(path.stat().st_size)
    content = path.read_bytes()
    enforce_image_dimension_limit(content)
    return VisionInput(
        content=content,
        mime_type=getattr(file_input, "mime_type", None) or "image/png",
        file_name=getattr(file_input, "file_name", None),
        source_url=getattr(file_input, "file_uri", None),
    )


def _local_pdf_vision_input(file_input) -> VisionInput:
    local_path = getattr(file_input, "local_path", None) or getattr(
        file_input,
        "file_path",
        None,
    )
    path = Path(local_path).expanduser().resolve(strict=True)
    enforce_file_size_limit(path.stat().st_size)
    content = path.read_bytes()
    return VisionInput(
        content=content,
        mime_type="application/pdf",
        file_name=getattr(file_input, "file_name", None),
        source_url=getattr(file_input, "file_uri", None),
    )


def _is_local_pdf_input(file_input) -> bool:
    local_path = getattr(file_input, "local_path", None) or getattr(
        file_input,
        "file_path",
        None,
    )
    return bool(local_path) and getattr(file_input, "mime_type", None) == "application/pdf"


def _pdf_loader_metadata(metadata: dict) -> dict:
    return {
        "implementation_status": metadata.get("implementation_status"),
        "needs_ocr": metadata.get("needs_ocr"),
        "source": metadata.get("source"),
    }
