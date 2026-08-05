import logging
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth import require_oa_token, require_web_console_user
from app.core.config import settings
from app.integrations.mysql_client import MySqlFetchClient, mysql_settings_from_env
from app.integrations.starrocks.tobacco_license_sources import (
    SqlFetchClient,
    build_pending_stores_sql,
    fetch_pending_stores,
    fetch_latest_tobacco_license_source_files,
    TobaccoLicenseSourceTaskError,
)
from app.models import (
    ReviewInput,
    ReviewInputContext,
    ReviewResult,
    ReviewStatus,
)
from app.repositories import build_review_result_repository_from_env
from app.services.review_service import ReviewService
from app.services.oa_auto_review_callback import (
    HttpOaAutoReviewCallbackClient,
    OaAutoReviewCallbackClient,
    OaAutoReviewCallbackPayload,
)
from app.services.oa_tobacco_auto_review import (
    OaAutoReviewCommand,
    OaAutoReviewOutcome,
    OaTobaccoAutoReviewService,
    _oa_source_snapshot,
    oa_auto_review_task_id,
)
from app.services.tobacco_consistency_extraction import (
    extract_consistency_document_results,
    resolved_consistency_fields,
)
from app.services.tobacco_license_files import (
    TobaccoLicenseFileStore,
    TobaccoLicenseFileStoreError,
)
from app.services.tobacco_rpa_verification import execute_tobacco_rpa_verification
from app.services.tobacco_review_cache import save_tobacco_report
from app.use_cases.tobacco_license_consistency_review import (
    tobacco_license_consistency_review_use_case,
)
from app.workflows.tobacco_license_consistency_review.decision import (
    oa_review_decision,
)


router = APIRouter(
    prefix="/api/v1/tobacco-license-consistency",
    tags=["tobacco-license-consistency"],
)
logger = logging.getLogger(__name__)


class CreateConsistencyReviewRequest(BaseModel):
    store_identifier: str
    review_mode: Literal["standard", "store_in_store"] = "standard"
    business_license_fields: dict[str, Any] = Field(default_factory=dict)
    tobacco_license_fields: dict[str, Any] = Field(default_factory=dict)
    store_in_store: dict[str, Any] = Field(default_factory=dict)
    selected_files: list[dict[str, Any]] = Field(default_factory=list)


class TobaccoManualReviewRequest(BaseModel):
    decision: Literal["APPROVE", "REJECT", "REQUEST_MORE_INFO"]
    comment: str = ""


class BatchConsistencyReviewRequest(BaseModel):
    store_identifiers: list[str] = Field(min_length=1, max_length=20)


class OaAutoReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requestid: int = Field(gt=0)
    store_code: str = Field(min_length=1, max_length=128)
    store_name: str | None = Field(default=None, max_length=256)
    workflow_id: int = Field(gt=0)
    callback_url: str | None = None

    @field_validator("store_code")
    @classmethod
    def strip_store_code(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("store_code must not be blank")
        return value.strip()

    @field_validator("callback_url")
    @classmethod
    def allow_only_empty_legacy_callback(cls, value: str | None) -> None:
        if value is not None and value.strip():
            raise ValueError("callback_url is not supported")
        return None


def get_starrocks_sql_client() -> SqlFetchClient:
    return MySqlFetchClient(mysql_settings_from_env("STARROCKS"))


def get_file_store() -> TobaccoLicenseFileStore:
    return TobaccoLicenseFileStore()


def get_review_repository():
    return build_review_result_repository_from_env()


def get_document_review_service(
    repository=Depends(get_review_repository),
) -> ReviewService:
    return ReviewService(repository=repository)


def get_oa_auto_review_callback_client() -> OaAutoReviewCallbackClient:
    try:
        return HttpOaAutoReviewCallbackClient(settings.oa_auto_review_callback_url)
    except ValueError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "OA_CALLBACK_NOT_CONFIGURED",
                "message": "OA 审核结果回调地址未配置",
            },
        ) from error


@router.get("/pending-stores")
def list_pending_stores(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _current_user: dict[str, Any] = Depends(require_web_console_user),
    sql_client: SqlFetchClient = Depends(get_starrocks_sql_client),
) -> dict[str, Any]:
    """返回有待处理 OA 烟草证提交流程的门店列表"""
    try:
        rows = fetch_pending_stores(
            sql_client,
            sql=build_pending_stores_sql(page=page, page_size=page_size + 1),
        )
        stores = rows[:page_size]
    except TobaccoLicenseSourceTaskError as error:
        raise HTTPException(
            status_code=400,
            detail={
                "code": error.code,
                "message": str(error),
            },
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "STARROCKS_UNAVAILABLE",
                "message": f"StarRocks 不可用，无法获取待处理列表: {error}",
            },
        ) from error

    return {
        "stores": stores,
        "page": page,
        "page_size": page_size,
        "has_more": len(rows) > page_size,
    }


@router.post("/reviews")
def create_consistency_review(
    request: CreateConsistencyReviewRequest,
    _current_user: dict[str, Any] = Depends(require_web_console_user),
    sql_client: SqlFetchClient = Depends(get_starrocks_sql_client),
    file_store: TobaccoLicenseFileStore = Depends(get_file_store),
    repository=Depends(get_review_repository),
    document_review_service: ReviewService = Depends(get_document_review_service),
) -> dict[str, Any]:
    """获取门店来源文件并触发营业执照与烟草证一致性比对"""
    store_identifier = request.store_identifier.strip()
    if not store_identifier:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "STORE_IDENTIFIER_EMPTY",
                "message": "门店标识不能为空",
            },
        )

    # 1. 查询 StarRocks 获取来源文件
    try:
        source_files = fetch_latest_tobacco_license_source_files(
            sql_client,
            store_identifier,
        )
    except TobaccoLicenseSourceTaskError as error:
        raise HTTPException(
            status_code=400,
            detail={
                "code": error.code,
                "message": str(error),
                "store_identifier": store_identifier,
            },
        ) from error

    if not source_files:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "SOURCE_RECORD_NOT_FOUND",
                "message": "未找到该门店的烟草证来源记录",
                "store_identifier": store_identifier,
            },
        )

    # 2. 证照字段必须来自文件抽取或人工确认，不能用 OA 门店名称伪造。
    first = source_files[0]
    store_name = first.store_name or first.store_code or store_identifier
    business_fields = dict(request.business_license_fields)
    tobacco_fields = dict(request.tobacco_license_fields)

    # 3. 尝试存储来源文件（可能因为 NAS 不可用而失败，但不阻断流程）
    stored_documents = []
    try:
        stored_documents = file_store.store_source_files(source_files)
    except TobaccoLicenseFileStoreError:
        pass  # 文件存储失败不影响比对流程

    document_results = {}
    extraction_errors = {}
    if stored_documents:
        document_results, extraction_errors = extract_consistency_document_results(
            stored_documents,
            review_service=document_review_service,
            store_identifier=store_identifier,
        )

    business_fields = resolved_consistency_fields(
        document_results.get("business_license"),
        request.business_license_fields,
    )
    tobacco_fields = resolved_consistency_fields(
        document_results.get("tobacco_license"),
        request.tobacco_license_fields,
    )
    oa_source = _oa_source_snapshot(
        first,
        source_files=source_files,
        stored_documents=stored_documents,
        selected_files=request.selected_files,
    )
    oa_source["document_extraction"] = {
        role: {
            "task_id": result.task_id,
            "status": result.status.value,
            "document_type": result.document_type,
        }
        for role, result in document_results.items()
    }
    if extraction_errors:
        oa_source["document_extraction_errors"] = extraction_errors

    # 4. 构建输入并执行一致性比对
    review_input = ReviewInput(
        supplier_name=store_name,
        supplier_credit_code="",
        declared_document_type="business_tobacco_consistency",
        source={
            "store_identifier": store_identifier,
            "requestid": first.requestid,
            "oa": oa_source,
        },
        options={
            "review_mode": request.review_mode,
            "business_license_fields": business_fields,
            "tobacco_license_fields": tobacco_fields,
            "business_license_result": document_results.get("business_license"),
            "tobacco_license_result": document_results.get("tobacco_license"),
            "store_in_store": request.store_in_store,
            "selected_files": request.selected_files,
        },
    )

    task_id = _generate_task_id(store_identifier)
    input_context = ReviewInputContext(
        task_id=task_id,
        input=review_input,
        use_case_name=tobacco_license_consistency_review_use_case.name,
        use_case_version=tobacco_license_consistency_review_use_case.version,
        ruleset_version=tobacco_license_consistency_review_use_case.ruleset_version,
    )

    try:
        result = tobacco_license_consistency_review_use_case.review(input_context)
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "CONSISTENCY_REVIEW_FAILED",
                "message": f"一致性比对执行失败: {error}",
            },
        ) from error

    # 5. 从规则结果中提取比对结论
    rule_results = result.rule_results or []
    unmatched = [r.rule_name for r in rule_results if not r.passed]
    has_validity_issue = any(not r.passed and "VALIDITY" in (r.rule_code or "") for r in rule_results)

    report = {
        "id": result.task_id,
        "company_name": store_name,
        "review_mode": request.review_mode,
        "overall_result": "待校验" if result.needs_manual_review else ("通过" if result.risk_level.value == "NONE" else "不通过"),
        "compare_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "unmatched_fields": unmatched,
        "name_match": "不匹配" if any(not rule.passed and "SUBJECT_NAME" in (rule.rule_code or "") for rule in rule_results) else "匹配",
        "address_match": "不匹配" if any(not rule.passed and "ADDRESS" in (rule.rule_code or "") for rule in rule_results) else "匹配",
        "person_match": "不匹配" if any(not rule.passed and "PERSON" in (rule.rule_code or "") for rule in rule_results) else "匹配",
        "type_match": "正确",
        "validity_status": "已过期" if has_validity_issue else "未过期",
        "business_license_name": business_fields.get("subject_name"),
        "business_license_address": business_fields.get("business_address"),
        "business_license_person": business_fields.get("legal_person"),
        "tobacco_license_name": tobacco_fields.get("subject_name"),
        "tobacco_license_no": tobacco_fields.get("license_no"),
        "tobacco_license_address": tobacco_fields.get("business_address"),
        "tobacco_license_person": tobacco_fields.get("legal_person"),
        "comparison": dict(result.skill_result.get("comparison") or {}),
        "rule_results": [rule.model_dump(mode="json") for rule in rule_results],
        "needs_manual_review": result.needs_manual_review,
        "risk_level": result.risk_level.value,
        "source_request_id": first.requestid,
        "oa": oa_source,
    }
    # 6. 执行官网 RPA 验真，再统一保存最终结果。
    report["rpa_verification"] = execute_tobacco_rpa_verification(
        result=result,
        task_id=task_id,
        certificate_no=str(tobacco_fields.get("license_no") or "").strip(),
        store_name=store_name,
        requestid=str(first.requestid or ""),
    )
    try:
        repository.save(result)
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail={"code": "RESULT_STORE_UNAVAILABLE", "message": "审核结果保存失败"},
        ) from error
    save_tobacco_report(report)
    return {
        "task_id": result.task_id,
        "summary": result.summary,
        "status": result.status.value,
        "risk_level": result.risk_level.value,
        "needs_manual_review": result.needs_manual_review,
        "report": report,
    }


def create_oa_auto_review(
    request: OaAutoReviewRequest,
    _oa_client: dict[str, str] = Depends(require_oa_token),
    sql_client: SqlFetchClient = Depends(get_starrocks_sql_client),
    file_store: TobaccoLicenseFileStore = Depends(get_file_store),
    repository=Depends(get_review_repository),
    document_review_service: ReviewService = Depends(get_document_review_service),
) -> dict[str, Any]:
    """按 OA 请求身份同步执行烟草证一致性自动审核。"""
    outcome = OaTobaccoAutoReviewService(
        sql_client=sql_client,
        file_store=file_store,
        repository=repository,
        document_review_service=document_review_service,
    ).review(
        OaAutoReviewCommand(
            requestid=request.requestid,
            store_code=request.store_code,
            store_name=request.store_name,
            workflow_id=request.workflow_id,
        )
    )
    return _oa_outcome_response(outcome)


@router.post("/oa-auto-review")
def submit_oa_auto_review(
    request: OaAutoReviewRequest,
    background_tasks: BackgroundTasks,
    _oa_client: dict[str, str] = Depends(require_oa_token),
    sql_client: SqlFetchClient = Depends(get_starrocks_sql_client),
    file_store: TobaccoLicenseFileStore = Depends(get_file_store),
    repository=Depends(get_review_repository),
    document_review_service: ReviewService = Depends(get_document_review_service),
    callback_client: OaAutoReviewCallbackClient = Depends(
        get_oa_auto_review_callback_client
    ),
) -> dict[str, Any]:
    """受理 OA 烟草证审核，并在后台完成后推送结果。"""
    command = OaAutoReviewCommand(
        requestid=request.requestid,
        store_code=request.store_code,
        store_name=request.store_name,
        workflow_id=request.workflow_id,
    )
    task_id = oa_auto_review_task_id(command.workflow_id, command.requestid)
    background_tasks.add_task(
        _run_oa_auto_review_and_callback,
        command=command,
        review_service=OaTobaccoAutoReviewService(
            sql_client=sql_client,
            file_store=file_store,
            repository=repository,
            document_review_service=document_review_service,
        ),
        callback_client=callback_client,
    )
    return {
        "code": 0,
        "message": "accepted",
        "data": {
            "status": "processing",
            "task_id": task_id,
            "workflow_id": command.workflow_id,
        },
    }


def _run_oa_auto_review_and_callback(
    *,
    command: OaAutoReviewCommand,
    review_service: OaTobaccoAutoReviewService,
    callback_client: OaAutoReviewCallbackClient,
) -> None:
    task_id = oa_auto_review_task_id(command.workflow_id, command.requestid)
    try:
        outcome = review_service.review(command)
        if outcome.error is not None and outcome.error.code == "REVIEW_IN_PROGRESS":
            logger.info("OA 自动审核任务已由其他执行者处理: task_id=%s", task_id)
            return
        result = _oa_outcome_response(outcome)
    except Exception:
        logger.exception("OA 自动审核后台执行失败: task_id=%s", task_id)
        result = _oa_exception_response(
            task_id,
            "AUTO_REVIEW_FAILED",
            "自动审核执行失败",
            retryable=True,
        )

    payload = OaAutoReviewCallbackPayload(
        workflow_id=command.workflow_id,
        requestid=command.requestid,
        store_code=command.store_code,
        result=result,
    )
    try:
        callback_client.send(payload)
    except Exception:
        logger.exception("OA 审核结果回调失败: task_id=%s", task_id)


@router.post("/reviews/batch")
def create_consistency_reviews_batch(
    request: BatchConsistencyReviewRequest,
    current_user: dict[str, Any] = Depends(require_web_console_user),
    sql_client: SqlFetchClient = Depends(get_starrocks_sql_client),
    file_store: TobaccoLicenseFileStore = Depends(get_file_store),
    repository=Depends(get_review_repository),
) -> dict[str, Any]:
    """Submit selected OA stores as one batch and return each review outcome."""
    store_identifiers = list(dict.fromkeys(
        identifier.strip()
        for identifier in request.store_identifiers
        if identifier and identifier.strip()
    ))
    if not store_identifiers:
        raise HTTPException(status_code=400, detail={"code": "STORE_IDENTIFIERS_EMPTY", "message": "请至少选择一条待处理申请"})

    items: list[dict[str, Any]] = []
    for store_identifier in store_identifiers:
        payload = {"store_identifier": store_identifier}
        try:
            result = create_consistency_review(
                request=CreateConsistencyReviewRequest(**payload),
                _current_user=current_user,
                sql_client=sql_client,
                file_store=file_store,
                repository=repository,
                document_review_service=ReviewService(repository=repository),
            )
            items.append({
                "store_identifier": store_identifier,
                "status": "completed",
                "task_id": result["task_id"],
                "report": result["report"],
            })
        except HTTPException as error:
            items.append({
                "store_identifier": store_identifier,
                "status": "failed",
                "error": error.detail,
            })
        except Exception as error:
            items.append({
                "store_identifier": store_identifier,
                "status": "failed",
                "error": {"code": "BATCH_REVIEW_FAILED", "message": str(error)},
            })
    return {
        "total": len(items),
        "completed": sum(item["status"] == "completed" for item in items),
        "failed": sum(item["status"] == "failed" for item in items),
        "items": items,
    }


@router.post("/reviews/{task_id}/manual-review")
def manual_review_consistency_result(
    task_id: str,
    request: TobaccoManualReviewRequest,
    _current_user: dict[str, Any] = Depends(require_web_console_user),
    repository=Depends(get_review_repository),
) -> dict[str, Any]:
    decision = {
        "APPROVE": "approved",
        "REJECT": "rejected",
        "REQUEST_MORE_INFO": "request_more_info",
    }[request.decision]
    reviewer_id = str(
        _current_user.get("external_id") or _current_user.get("username") or "web-reviewer"
    )
    detail = repository.manual_review_qc_review(
        task_id=task_id,
        decision=decision,
        comment=request.comment.strip(),
        reviewer_id=reviewer_id,
        reviewer_username=str(_current_user.get("username") or ""),
        reviewed_at=datetime.now().astimezone(),
    )
    if detail is None:
        raise HTTPException(status_code=404, detail={"code": "REVIEW_NOT_FOUND", "message": "比对报告不存在"})
    payload = repository.get_by_task_id(task_id)
    return {
        "report": detail,
        "payload": payload.model_dump(mode="json") if payload is not None else None,
    }


@router.get("/reviews/{task_id}/oa-result")
def get_consistency_oa_result(
    task_id: str,
    _oa_client: dict[str, str] = Depends(require_oa_token),
    repository=Depends(get_review_repository),
) -> dict[str, Any]:
    """提供给 OA 适配器的回传载荷。

    从 review_results 表直接读取一致性比对 + RPA 验真结果，
    不再依赖内存缓存，确保数据始终与库表一致。
    """
    # 1. 从 review_results 表读取完整 payload
    payload = repository.get_by_task_id(task_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "REVIEW_NOT_FOUND", "message": "比对结果不存在"},
        )

    decision = oa_review_decision(payload)
    status_label = {
        "pass": "通过",
        "reject": "不通过",
        "manual_review": "待校验",
        "exception": "异常",
    }[decision]
    source_raw = {}
    if isinstance(payload.skill_result, dict):
        source_raw = dict(payload.skill_result.get("source_evidence", {}) or {}).get("source", {})
    requestid = source_raw.get("requestid")
    rpa_info = (
        payload.skill_result.get("rpa_verification")
        if isinstance(payload.skill_result, dict)
        else None
    )
    oa_rpa_info = _oa_rpa_view(rpa_info)
    progress_error = (
        {
            "code": "REVIEW_IN_PROGRESS",
            "message": "自动审核正在执行，请稍后轮询",
            "retryable": True,
        }
        if payload.status == ReviewStatus.RUNNING
        else None
    )

    return {
        "code": 0,
        "message": "success",
        "data": {
            "callback": {
                "requestid": requestid,
                "review_task_id": payload.task_id,
                "review_mode": source_raw.get("oa", {}).get("review_mode"),
                "decision": decision,
                "review_status": status_label,
                "risk_level": payload.risk_level.value,
                "needs_manual_review": decision in {"manual_review", "exception"},
                "summary": (
                    "系统无法自动完成核对，需人工处理"
                    if decision == "exception"
                    else payload.summary
                ),
                "rule_results": [
                    rule.model_dump(mode="json") for rule in payload.rule_results
                ],
                "manual_review": (
                    payload.manual_review.model_dump(mode="json")
                    if payload.manual_review
                    else None
                ),
                "completed_at": payload.updated_at or payload.created_at,
                "rpa_verification": oa_rpa_info,
                "error": progress_error,
            },
        }
    }


def _generate_task_id(store_identifier: str) -> str:
    import hashlib
    import time

    raw = f"tobacco-consistency-{store_identifier}-{time.time_ns()}"
    return f"tc-{hashlib.md5(raw.encode()).hexdigest()[:16]}"


def _oa_response(result: ReviewResult) -> dict[str, Any]:
    decision = oa_review_decision(result)
    failed = [rule for rule in result.rule_results if not rule.passed]
    rpa_info = (
        result.skill_result.get("rpa_verification")
        if isinstance(result.skill_result, dict)
        else None
    )
    data: dict[str, Any] = {
        "decision": decision,
        "task_id": result.task_id,
        "summary": (
            "系统无法自动完成核对，需人工处理"
            if decision == "exception"
            else result.summary
        ),
        "rule_results": [rule.model_dump(mode="json") for rule in result.rule_results],
        "needs_manual_review": decision in {"manual_review", "exception"},
    }
    if decision == "reject":
        reject_reasons = [
            {
                "rule_code": rule.rule_code,
                "rule_name": rule.rule_name,
                "message": rule.message,
            }
            for rule in failed
        ]
        if isinstance(rpa_info, dict) and rpa_info.get("status") in {
            "FAILED",
            "SUSPECTED",
            "NOT_FOUND",
        }:
            reject_reasons.append(
                {
                    "rule_code": "TOBACCO_LICENSE_RPA_VERIFICATION",
                    "rule_name": "烟草证官网验真",
                    "message": "烟草证官网验真未通过",
                }
            )
        data["reject_reasons"] = reject_reasons
    if decision == "exception" and isinstance(rpa_info, dict):
        data["error"] = {
            "code": "RPA_VERIFICATION_FAILED",
            "message": "烟草证官网验真未可靠完成",
            "retryable": True,
        }
    return {"code": 0, "message": "success", "data": data}


def _oa_outcome_response(outcome: OaAutoReviewOutcome) -> dict[str, Any]:
    if outcome.result is not None:
        return _oa_response(outcome.result)
    assert outcome.error is not None
    return _oa_exception_response(
        outcome.task_id,
        outcome.error.code,
        outcome.error.message,
        retryable=outcome.error.retryable,
        details=outcome.error.details,
    )


def _oa_exception_response(
    task_id: str,
    code: str,
    message: str,
    *,
    retryable: bool,
    details: Any = None,
) -> dict[str, Any]:
    error = {"code": code, "message": message, "retryable": retryable}
    if details is not None:
        error["details"] = details
    return {
        "code": 0,
        "message": "success",
        "data": {
            "decision": "exception",
            "task_id": task_id,
            "summary": "系统无法自动完成核对，需人工处理",
            "needs_manual_review": True,
            "error": error,
        },
    }


def _oa_rpa_view(rpa_info: Any) -> dict[str, Any] | None:
    if not isinstance(rpa_info, dict):
        return None
    status = str(rpa_info.get("status") or "")
    payload = {
        key: rpa_info.get(key)
        for key in (
            "status",
            "certificate_no",
            "verified_at",
            "screenshot_url",
            "result_label",
            "attempts",
        )
        if key in rpa_info
    }
    if status == "ERROR":
        payload["error_message"] = "烟草证官网验真未可靠完成"
    return payload
