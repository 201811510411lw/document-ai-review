from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from app.integrations.starrocks.tobacco_license_sources import (
    SqlFetchClient,
    fetch_tobacco_license_source_files_by_request,
)
from app.models import (
    ManualReview,
    ManualReviewStatus,
    ReviewInput,
    ReviewInputContext,
    ReviewResult,
    ReviewStatus,
    RiskLevel,
)
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
class ReviewRepository(Protocol):
    def get_by_task_id(self, task_id: str) -> ReviewResult | None:
        ...

    def save(self, result: ReviewResult) -> None:
        ...

    def claim(self, result: ReviewResult) -> bool:
        ...

    def release_claim(self, result: ReviewResult) -> None:
        ...

    def complete_claim(self, claim: ReviewResult, result: ReviewResult) -> bool:
        ...


class OaAutoReviewCommand(BaseModel):
    requestid: int = Field(gt=0)
    store_code: str
    store_name: str | None = None
    workflow_id: int = Field(gt=0)


class OaAutoReviewError(BaseModel):
    code: str
    message: str
    retryable: bool
    details: Any = None


class OaAutoReviewOutcome(BaseModel):
    task_id: str
    result: ReviewResult | None = None
    error: OaAutoReviewError | None = None


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
        task_id = oa_auto_review_task_id(command.workflow_id, command.requestid)
        return self._review_once(task_id, command)

    def _review_once(
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
            existing_outcome = self._existing_outcome(task_id, existing)
            if existing_outcome is not None:
                return existing_outcome

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

        claim = _claim_result(task_id, command)
        try:
            claimed = self._repository.claim(claim)
        except Exception:
            return _error(
                task_id,
                "RESULT_STORE_UNAVAILABLE",
                "审核结果存储不可用",
                retryable=True,
            )
        if not claimed:
            existing = self._repository.get_by_task_id(task_id)
            if existing is not None:
                return self._existing_outcome(task_id, existing) or _error(
                    task_id,
                    "REVIEW_IN_PROGRESS",
                    "自动审核正在执行，请稍后轮询",
                    retryable=True,
                )
            return _error(
                task_id,
                "REVIEW_IN_PROGRESS",
                "自动审核正在执行，请稍后轮询",
                retryable=True,
            )

        try:
            stored_documents = self._file_store.store_source_files(source_files)
        except Exception:
            return self._error_after_release(
                claim,
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
            return self._error_after_release(
                claim,
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
            return self._error_after_release(
                claim,
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
        rpa_started = False
        try:
            result = tobacco_license_consistency_review_use_case.review(input_context)
            tobacco_fields = resolved_consistency_fields(
                document_results.get("tobacco_license"), {}
            )
            certificate_no = str(tobacco_fields.get("license_no") or "").strip()
            if certificate_no:
                rpa_payload = execute_tobacco_rpa_verification(
                    result=result,
                    task_id=task_id,
                    certificate_no=certificate_no,
                    store_name=store_name,
                    requestid=str(command.requestid),
                )
                rpa_started = rpa_payload is not None
            if not self._repository.complete_claim(claim, result):
                return _error(
                    task_id,
                    "REVIEW_CLAIM_LOST",
                    "自动审核任务占位已失效，结果未写入",
                    retryable=False,
                )
        except Exception:
            if rpa_started:
                return _error(
                    task_id,
                    "RESULT_STORE_UNAVAILABLE",
                    "官网验真已执行，但最终结果保存失败，需人工处理",
                    retryable=False,
                )
            return self._error_after_release(
                claim,
                task_id,
                "AUTO_REVIEW_FAILED",
                "自动审核执行或保存失败",
                retryable=True,
            )
        return OaAutoReviewOutcome(task_id=task_id, result=result)

    def _existing_outcome(
        self,
        task_id: str,
        existing: ReviewResult,
    ) -> OaAutoReviewOutcome | None:
        if existing.status != ReviewStatus.RUNNING:
            return OaAutoReviewOutcome(task_id=task_id, result=existing)
        return _error(
            task_id,
            "REVIEW_IN_PROGRESS",
            "自动审核正在执行，请稍后轮询",
            retryable=True,
        )

    def _error_after_release(
        self,
        claim: ReviewResult,
        task_id: str,
        code: str,
        message: str,
        *,
        retryable: bool,
        details: Any = None,
    ) -> OaAutoReviewOutcome:
        try:
            self._repository.release_claim(claim)
        except Exception:
            return _error(
                task_id,
                "RESULT_STORE_UNAVAILABLE",
                "审核结果存储不可用",
                retryable=True,
            )
        return _error(
            task_id,
            code,
            message,
            retryable=retryable,
            details=details,
        )


def oa_auto_review_task_id(workflow_id: int, requestid: int) -> str:
    return f"tc-oa-{workflow_id}-{requestid}"


def _claim_result(task_id: str, command: OaAutoReviewCommand) -> ReviewResult:
    now = datetime.now(timezone.utc)
    return ReviewResult(
        task_id=task_id,
        use_case_name="tobacco_license_consistency_review",
        use_case_version="v1",
        skill_name="tobacco_license_consistency_review",
        skill_version="v1",
        ruleset_version="tobacco-license-consistency-rules-v1",
        document_type="business_tobacco_consistency",
        status=ReviewStatus.RUNNING,
        risk_level=RiskLevel.NONE,
        needs_manual_review=False,
        summary="OA 自动审核执行中",
        manual_review=ManualReview(status=ManualReviewStatus.NOT_REQUIRED),
        created_at=now,
        updated_at=now,
        skill_result={
            "oa_claim": {
                "claim_token": uuid4().hex,
                "requestid": command.requestid,
                "workflow_id": command.workflow_id,
            }
        },
    )


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
