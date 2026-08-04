from threading import Lock
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.integrations.starrocks.tobacco_license_sources import (
    SqlFetchClient,
    fetch_tobacco_license_source_files_by_request,
)
from app.models import ReviewInput, ReviewInputContext, ReviewResult
from app.services.tobacco_consistency_extraction import (
    DocumentReviewService,
    extract_consistency_document_results,
    resolved_consistency_fields,
)
from app.services.tobacco_license_files import TobaccoLicenseFileStore
from app.services.tobacco_rpa_verification import execute_tobacco_rpa_verification
from app.use_cases.tobacco_license_consistency_review import (
    tobacco_license_consistency_review_use_case,
)
from app.workflows.tobacco_license_consistency_review.decision import (
    oa_review_decision,
)


class ReviewRepository(Protocol):
    def get_by_task_id(self, task_id: str) -> ReviewResult | None:
        ...

    def save(self, result: ReviewResult) -> None:
        ...


class OaAutoReviewCommand(BaseModel):
    requestid: int = Field(gt=0)
    store_code: str
    store_name: str | None = None
    workflow_id: int = 614


class OaAutoReviewError(BaseModel):
    code: str
    message: str
    retryable: bool
    details: Any = None


class OaAutoReviewOutcome(BaseModel):
    task_id: str
    result: ReviewResult | None = None
    error: OaAutoReviewError | None = None


_task_locks_guard = Lock()
_task_locks: dict[str, Lock] = {}


class OaTobaccoAutoReviewService:
    def __init__(
        self,
        *,
        sql_client: SqlFetchClient,
        file_store: TobaccoLicenseFileStore,
        repository: ReviewRepository,
        document_review_service: DocumentReviewService,
    ) -> None:
        self._sql_client = sql_client
        self._file_store = file_store
        self._repository = repository
        self._document_review_service = document_review_service

    def review(self, command: OaAutoReviewCommand) -> OaAutoReviewOutcome:
        task_id = f"tc-oa-{command.workflow_id}-{command.requestid}"
        with _task_lock(task_id):
            return self._review_locked(task_id, command)

    def _review_locked(
        self,
        task_id: str,
        command: OaAutoReviewCommand,
    ) -> OaAutoReviewOutcome:
        try:
            existing = self._repository.get_by_task_id(task_id)
        except Exception:
            return _error(
                task_id,
                "RESULT_STORE_UNAVAILABLE",
                "审核结果存储不可用",
                retryable=True,
            )
        if existing is not None:
            return OaAutoReviewOutcome(task_id=task_id, result=existing)

        try:
            source_files = fetch_tobacco_license_source_files_by_request(
                self._sql_client,
                command.requestid,
                workflow_id=command.workflow_id,
            )
        except Exception:
            return _error(
                task_id,
                "SOURCE_QUERY_FAILED",
                "OA 来源查询失败",
                retryable=True,
            )
        if not source_files:
            return _error(
                task_id,
                "SOURCE_RECORD_NOT_READY",
                "未找到该 OA 请求的证照附件，请稍后重试",
                retryable=True,
            )
        if any(
            (source.store_code or "").strip() != command.store_code
            for source in source_files
        ):
            return _error(
                task_id,
                "SOURCE_IDENTITY_MISMATCH",
                "OA 请求中的门店编码与来源记录不一致",
                retryable=False,
            )

        try:
            stored_documents = self._file_store.store_source_files(source_files)
        except Exception:
            return _error(
                task_id,
                "SOURCE_FILE_PREPARATION_FAILED",
                "OA 附件准备失败",
                retryable=True,
            )

        document_results, extraction_errors = extract_consistency_document_results(
            stored_documents,
            review_service=self._document_review_service,
            store_identifier=command.store_code,
        )
        conflicting_roles = {
            key
            for key, value in extraction_errors.items()
            if value == "MULTIPLE_CONFLICTING_CANDIDATES"
        }
        technical_errors = {
            key: value
            for key, value in extraction_errors.items()
            if value != "MULTIPLE_CONFLICTING_CANDIDATES"
        }
        if technical_errors:
            return _error(
                task_id,
                "DOCUMENT_EXTRACTION_FAILED",
                "部分证照附件抽取失败",
                retryable=False,
                details={"attachments": sorted(technical_errors)},
            )
        missing_roles = {
            role
            for role in ("business_license", "tobacco_license")
            if role not in document_results
        }
        if missing_roles - conflicting_roles:
            return _error(
                task_id,
                "REQUIRED_DOCUMENT_MISSING",
                "OA 请求缺少必需证照附件",
                retryable=False,
                details={"missing_roles": sorted(missing_roles)},
            )

        first = source_files[0]
        store_name = first.store_name or command.store_name or command.store_code
        oa_source = _oa_source_snapshot(
            first,
            source_files=source_files,
            stored_documents=stored_documents,
            selected_files=[],
        )
        if conflicting_roles:
            oa_source["document_extraction_errors"] = {
                role: "MULTIPLE_CONFLICTING_CANDIDATES"
                for role in sorted(conflicting_roles)
            }
        review_input = ReviewInput(
            supplier_name=store_name,
            supplier_credit_code="",
            declared_document_type="business_tobacco_consistency",
            source={
                "store_identifier": command.store_code,
                "requestid": command.requestid,
                "workflow_id": command.workflow_id,
                "oa": oa_source,
            },
            options={
                "review_mode": "standard",
                "business_license_result": document_results.get("business_license"),
                "tobacco_license_result": document_results.get("tobacco_license"),
            },
        )
        input_context = ReviewInputContext(
            task_id=task_id,
            input=review_input,
            use_case_name=tobacco_license_consistency_review_use_case.name,
            use_case_version=tobacco_license_consistency_review_use_case.version,
            ruleset_version=tobacco_license_consistency_review_use_case.ruleset_version,
        )
        try:
            result = tobacco_license_consistency_review_use_case.review(input_context)
            if oa_review_decision(result) == "pass":
                tobacco_fields = resolved_consistency_fields(
                    document_results.get("tobacco_license"), {}
                )
                execute_tobacco_rpa_verification(
                    result=result,
                    task_id=task_id,
                    certificate_no=str(tobacco_fields.get("license_no") or "").strip(),
                    store_name=store_name,
                    requestid=str(command.requestid),
                )
            self._repository.save(result)
        except Exception:
            return _error(
                task_id,
                "AUTO_REVIEW_FAILED",
                "自动审核执行或保存失败",
                retryable=True,
            )
        return OaAutoReviewOutcome(task_id=task_id, result=result)


def _task_lock(task_id: str) -> Lock:
    with _task_locks_guard:
        return _task_locks.setdefault(task_id, Lock())


def _error(
    task_id: str,
    code: str,
    message: str,
    *,
    retryable: bool,
    details: Any = None,
) -> OaAutoReviewOutcome:
    return OaAutoReviewOutcome(
        task_id=task_id,
        error=OaAutoReviewError(
            code=code,
            message=message,
            retryable=retryable,
            details=details,
        ),
    )


def _oa_source_snapshot(
    first,
    *,
    source_files: list,
    stored_documents: list,
    selected_files: list[dict[str, Any]],
) -> dict[str, Any]:
    attachments = []
    stored_docids = set()
    for document in stored_documents:
        stored_docids.add(document.source.docid)
        for stored_file in document.files:
            attachments.append(
                {
                    "document_role": document.source.document_role,
                    "docid": document.source.docid,
                    "doc_subject": document.source.doc_subject,
                    "file_name": stored_file.file_name,
                    "relative_path": stored_file.relative_path,
                }
            )
    for source_file in source_files:
        if source_file.docid in stored_docids:
            continue
        attachments.append(
            {
                "document_role": source_file.document_role,
                "docid": source_file.docid,
                "doc_subject": source_file.doc_subject,
                "file_name": source_file.real_filename or source_file.docimage_filename,
                "relative_path": None,
            }
        )
    attachments.extend(
        {
            "document_role": "selected_attachment",
            "file_name": item.get("file_name"),
            "relative_path": item.get("relative_path"),
        }
        for item in selected_files
        if item.get("relative_path")
    )
    deduplicated = []
    seen = set()
    for attachment in attachments:
        key = (
            attachment.get("docid"),
            attachment.get("file_name"),
            attachment.get("relative_path"),
        )
        if key not in seen:
            seen.add(key)
            deduplicated.append(attachment)
    return {
        "requestid": first.requestid,
        "workflow_id": first.workflow_id,
        "request_name": first.request_name,
        "summary_title": first.summary_title,
        "content_summary": first.content_summary,
        "created_date": first.created_date,
        "created_time": first.created_time,
        "request_status": first.request_status,
        "attachments": deduplicated,
    }
