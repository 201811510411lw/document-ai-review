from collections.abc import Iterable
from typing import Any, Protocol

from app.models import ReviewDocumentInput, ReviewInput, ReviewResult
from app.services.tobacco_license_files import TobaccoLicenseStoredDocument


class DocumentReviewService(Protocol):
    def review(self, review_input: ReviewInput, use_case_name: str | None = None) -> ReviewResult:
        ...


_DOCUMENT_TYPES_BY_ROLE = {
    "business_license": "business_license",
    "tobacco_license": "tobacco_license",
}

_MANUAL_OVERRIDE_FIELDS = {
    "subject_name",
    "business_address",
    "legal_person",
    "license_no",
    "valid_from",
    "valid_to",
}

def extract_consistency_document_results(
    stored_documents: Iterable[TobaccoLicenseStoredDocument],
    *,
    review_service: DocumentReviewService,
    store_identifier: str,
) -> tuple[dict[str, ReviewResult], dict[str, str]]:
    """Review the current OA attachments using their document-specific workflow."""
    results: dict[str, ReviewResult] = {}
    errors: dict[str, str] = {}
    for document in stored_documents:
        role = document.source.document_role
        document_type = _DOCUMENT_TYPES_BY_ROLE.get(role)
        if document_type is None or role in results or not document.files:
            continue

        review_input = _review_input_for_document(
            document,
            store_identifier=store_identifier,
            document_type=document_type,
        )
        try:
            results[role] = review_service.review(
                review_input,
                use_case_name=document_type,
            )
        except Exception as error:
            errors[role] = f"{type(error).__name__}: {error}"
    return results, errors


def resolved_consistency_fields(
    review_result: ReviewResult | None,
    manual_fields: dict[str, Any],
) -> dict[str, Any]:
    """Use document-extracted values first; apply only non-empty manual corrections."""
    fields = _review_result_fields(review_result)
    for field, value in manual_fields.items():
        if field not in _MANUAL_OVERRIDE_FIELDS or not _has_text(value):
            continue
        fields[field] = value.strip() if isinstance(value, str) else value
    return fields


def _review_result_fields(review_result: ReviewResult | None) -> dict[str, Any]:
    if review_result is None:
        return {}
    skill_result = review_result.skill_result
    payload = skill_result if isinstance(skill_result, dict) else skill_result.model_dump(mode="json")
    fields = payload.get("normalized_fields") or payload.get("extracted_fields") or {}
    return dict(fields) if isinstance(fields, dict) else {}


def _review_input_for_document(
    document: TobaccoLicenseStoredDocument,
    *,
    store_identifier: str,
    document_type: str,
) -> ReviewInput:
    stored_file = document.files[0]
    role = document.source.document_role
    requestid = document.source.requestid
    docid = document.source.docid
    imagefile_id = document.source.imagefile_id
    return ReviewInput(
        # Do not seed OCR with OA fields. The document is the only evidence source.
        supplier_name="",
        supplier_credit_code="",
        declared_document_type=document_type,
        file=ReviewDocumentInput(
            local_path=stored_file.local_path,
            file_name=stored_file.file_name,
            mime_type=stored_file.content_type,
        ),
        source={
            "source_system": "oa_starrocks",
            "record_id": f"{store_identifier}-{requestid}-{docid}-{imagefile_id}-{role}",
            "attachment_ref_id": f"oa:{requestid}:{docid}:{imagefile_id}",
            "store_identifier": store_identifier,
            "requestid": requestid,
            "document_role": role,
            "relative_path": stored_file.relative_path,
        },
    )


def _has_text(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))
