import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from app.integrations.starrocks.tobacco_license_sources import (
    SqlFetchClient,
    fetch_tobacco_license_source_files_by_request,
)
from app.models import (
    AuditEvent,
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


logger = logging.getLogger(__name__)
OA_CLAIM_TIMEOUT = timedelta(minutes=15)


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
            logger.info(
                "[OA自动审核][来源查询开始] task_id=%s requestid=%s workflow_id=%s",
                task_id,
                command.requestid,
                command.workflow_id,
            )
            source_files = fetch_tobacco_license_source_files_by_request(
                self._sql_client,
                command.requestid,
                workflow_id=command.workflow_id,
            )
            logger.info(
                "[OA自动审核][来源查询完成] task_id=%s requestid=%s 附件数量=%s",
                task_id,
                command.requestid,
                len(source_files),
            )
        except Exception:
            logger.exception(
                "[OA自动审核][来源查询失败] task_id=%s requestid=%s",
                task_id,
                command.requestid,
            )
            return self._error_after_release(
                claim,
                task_id,
                "SOURCE_QUERY_FAILED",
                "OA 来源查询失败",
                retryable=True,
            )
        if not source_files:
            return self._error_after_release(
                claim,
                task_id,
                "SOURCE_RECORD_NOT_READY",
                "未找到该 OA 请求的证照附件，请稍后重试",
                retryable=True,
            )
        if any(
            (source.store_code or "").strip() != command.store_code
            for source in source_files
        ):
            return self._error_after_release(
                claim,
                task_id,
                "SOURCE_IDENTITY_MISMATCH",
                "OA 请求中的门店编码与来源记录不一致",
                retryable=False,
            )

        try:
            logger.info(
                "[OA自动审核][NAS文件准备开始] task_id=%s requestid=%s 附件数量=%s",
                task_id,
                command.requestid,
                len(source_files),
            )
            stored_documents = self._file_store.store_source_files(source_files)
            logger.info(
                "[OA自动审核][NAS文件准备完成] task_id=%s requestid=%s 文件数量=%s",
                task_id,
                command.requestid,
                sum(len(document.files) for document in stored_documents),
            )
            oa_source = _oa_source_snapshot(
                source_files[0],
                source_files=source_files,
                stored_documents=stored_documents,
                selected_files=[],
            )
            claim = self._persist_running_stage(
                claim,
                summary="OA 附件已落盘，正在执行证照抽取",
                skill_result={"source_evidence": {"source": oa_source}},
            )
        except Exception:
            logger.exception(
                "[OA自动审核][NAS文件准备失败] task_id=%s requestid=%s",
                task_id,
                command.requestid,
            )
            return self._error_after_release(
                claim,
                task_id,
                "SOURCE_FILE_PREPARATION_FAILED",
                "OA 附件准备失败",
                retryable=True,
            )

        logger.info(
            "[OA自动审核][OCR解析开始] task_id=%s requestid=%s",
            task_id,
            command.requestid,
        )
        document_results, extraction_errors = extract_consistency_document_results(
            stored_documents,
            review_service=self._document_review_service,
            store_identifier=command.store_code,
        )
        logger.info(
            "[OA自动审核][OCR解析完成] task_id=%s requestid=%s 证照角色=%s 抽取错误=%s",
            task_id,
            command.requestid,
            sorted(document_results),
            sorted(extraction_errors),
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

        extraction_snapshot = {
            "document_extraction": {
                role: {
                    "task_id": result.task_id,
                    "status": result.status.value,
                    "document_type": result.document_type,
                    "payload": result.model_dump(mode="json"),
                }
                for role, result in document_results.items()
            },
            "document_extraction_errors": extraction_errors,
        }
        try:
            claim = self._persist_running_stage(
                claim,
                summary="证照抽取完成，正在执行一致性规则",
                skill_result=extraction_snapshot,
            )
        except Exception:
            logger.exception("[OA自动审核][阶段保存失败] task_id=%s stage=extraction", task_id)
            return self._error_after_release(
                claim,
                task_id,
                "RESULT_STORE_UNAVAILABLE",
                "证照抽取阶段结果保存失败",
                retryable=True,
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
            logger.info(
                "[OA自动审核][规则校验开始] task_id=%s requestid=%s",
                task_id,
                command.requestid,
            )
            result = tobacco_license_consistency_review_use_case.review(input_context)
            logger.info(
                "[OA自动审核][规则校验完成] task_id=%s requestid=%s status=%s",
                task_id,
                command.requestid,
                result.status.value,
            )
            claim = self._persist_running_stage(
                claim,
                summary="一致性规则完成，正在保存最终审核结果",
                skill_result={
                    "business_license_fields": result.skill_result.get("business_license_fields", {}),
                    "tobacco_license_fields": result.skill_result.get("tobacco_license_fields", {}),
                    "comparison": result.skill_result.get("comparison", {}),
                    "source_evidence": result.skill_result.get("source_evidence", {}),
                    "extracted_fields": result.skill_result.get("extracted_fields", {}),
                    "normalized_fields": result.skill_result.get("normalized_fields", {}),
                    "rule_results": [rule.model_dump(mode="json") for rule in result.rule_results],
                },
            )
            tobacco_fields = resolved_consistency_fields(
                document_results.get("tobacco_license"), {}
            )
            certificate_no = str(tobacco_fields.get("license_no") or "").strip()
            if certificate_no:
                logger.info(
                    "[OA自动审核][RPA验真开始] task_id=%s requestid=%s",
                    task_id,
                    command.requestid,
                )
                rpa_payload = execute_tobacco_rpa_verification(
                    result=result,
                    task_id=task_id,
                    certificate_no=certificate_no,
                    store_name=store_name,
                    requestid=str(command.requestid),
                )
                rpa_started = rpa_payload is not None
                logger.info(
                    "[OA自动审核][RPA验真完成] task_id=%s requestid=%s 是否启动=%s",
                    task_id,
                    command.requestid,
                    rpa_started,
                )
            else:
                logger.info(
                    "[OA自动审核][RPA验真跳过] task_id=%s requestid=%s 原因=未识别许可证号",
                    task_id,
                    command.requestid,
                )
            if not self._repository.complete_claim(claim, result):
                return _error(
                    task_id,
                    "REVIEW_CLAIM_LOST",
                    "自动审核任务占位已失效，结果未写入",
                    retryable=False,
                )
            logger.info(
                "[OA自动审核][结果保存完成] task_id=%s requestid=%s",
                task_id,
                command.requestid,
            )
        except Exception:
            logger.exception(
                "[OA自动审核][审核执行失败] task_id=%s requestid=%s",
                task_id,
                command.requestid,
            )
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
        updated_at = existing.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - updated_at > OA_CLAIM_TIMEOUT:
            return self._error_after_release(
                existing,
                task_id,
                "AUTO_REVIEW_TIMEOUT",
                "自动审核超过处理时限，已转为失败并允许重试",
                retryable=True,
            )
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
        failure = claim.model_copy(
            update={
                "status": ReviewStatus.FAILED,
                "risk_level": RiskLevel.HIGH,
                "needs_manual_review": True,
                "summary": message,
                "manual_review": ManualReview(
                    status=ManualReviewStatus.PENDING,
                    reasons=[message],
                ),
                "audit_events": [
                    *claim.audit_events,
                    AuditEvent(
                        event_type="tobacco_license.oa.failed",
                        message=message,
                        occurred_at=datetime.now(timezone.utc),
                        details={"code": code, "retryable": retryable, "details": details},
                    ),
                ],
                "updated_at": datetime.now(timezone.utc),
                "skill_result": {
                    **(claim.skill_result if isinstance(claim.skill_result, dict) else {}),
                    "oa_error": {
                        "code": code,
                        "message": message,
                        "retryable": retryable,
                        "details": details,
                    },
                },
            }
        )
        try:
            self._repository.save(failure)
        except Exception:
            try:
                self._repository.release_claim(claim)
            except Exception:
                pass
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

    def _persist_running_stage(
        self,
        claim: ReviewResult,
        *,
        summary: str,
        skill_result: dict[str, Any],
    ) -> ReviewResult:
        stage = claim.model_copy(
            update={
                "summary": summary,
                "updated_at": datetime.now(timezone.utc),
                "skill_result": {
                    **(claim.skill_result if isinstance(claim.skill_result, dict) else {}),
                    **skill_result,
                },
            }
        )
        self._repository.save(stage)
        return stage


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
