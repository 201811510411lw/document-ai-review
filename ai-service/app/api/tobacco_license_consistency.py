from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.auth import require_web_console_user
from app.integrations.mysql_client import MySqlFetchClient, mysql_settings_from_env
from app.integrations.starrocks.tobacco_license_sources import (
    SqlFetchClient,
    build_pending_stores_sql,
    fetch_pending_stores,
    fetch_latest_tobacco_license_source_files,
    TobaccoLicenseSourceTaskError,
)
from app.models import ReviewInput, ReviewInputContext, ReviewResult
from app.repositories import build_review_result_repository_from_env
from app.services.review_service import ReviewService, review_service
from app.services.tobacco_license_files import (
    TobaccoLicenseFileStore,
    TobaccoLicenseFileStoreError,
)
from app.services.tobacco_license_demo import (
    demo_consistency_payload,
    demo_pending_stores,
    demo_source_files,
    is_demo_store,
)
from app.services.tobacco_review_cache import (
    apply_manual_review,
    get_tobacco_report,
    save_tobacco_report,
)
from app.use_cases.tobacco_license_consistency_review import (
    tobacco_license_consistency_review_use_case,
)


router = APIRouter(
    prefix="/api/v1/tobacco-license-consistency",
    tags=["tobacco-license-consistency"],
)


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


def get_starrocks_sql_client() -> SqlFetchClient:
    return MySqlFetchClient(mysql_settings_from_env("STARROCKS"))


def get_file_store() -> TobaccoLicenseFileStore:
    return TobaccoLicenseFileStore()


def get_review_repository():
    return build_review_result_repository_from_env()


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
        # 本地开发无法访问 StarRocks 时，保留一条明确标识的演示任务供工作台验收。
        all_stores = demo_pending_stores()
        offset = (page - 1) * page_size
        stores = all_stores[offset:offset + page_size]
        return {
            "stores": stores,
            "page": page,
            "page_size": page_size,
            "has_more": offset + page_size < len(all_stores),
            "source_unavailable": True,
        }

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
        source_files = (
            demo_source_files(store_identifier)
            if is_demo_store(store_identifier)
            else fetch_latest_tobacco_license_source_files(sql_client, store_identifier)
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
    if not is_demo_store(store_identifier):
        try:
            stored_documents = file_store.store_source_files(source_files)
        except TobaccoLicenseFileStoreError:
            pass  # 文件存储失败不影响比对流程
    oa_source = _oa_source_snapshot(
        first,
        source_files=source_files,
        stored_documents=stored_documents,
        selected_files=request.selected_files,
    )

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

    # 5. 保存审核结果
    try:
        repository.save(result)
    except Exception as error:
        # 结果保存失败不影响比对结果返回
        pass

    # 6. 从规则结果中提取比对结论
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
        "tobacco_license_address": tobacco_fields.get("business_address"),
        "tobacco_license_person": tobacco_fields.get("legal_person"),
        "comparison": dict(result.skill_result.get("comparison") or {}),
        "rule_results": [rule.model_dump(mode="json") for rule in rule_results],
        "needs_manual_review": result.needs_manual_review,
        "risk_level": result.risk_level.value,
        "source_request_id": first.requestid,
        "oa": oa_source,
    }
    save_tobacco_report(report)
    return {
        "task_id": result.task_id,
        "summary": result.summary,
        "status": result.status.value,
        "risk_level": result.risk_level.value,
        "needs_manual_review": result.needs_manual_review,
        "report": report,
    }


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
        if is_demo_store(store_identifier):
            payload.update(demo_consistency_payload(store_identifier))
        try:
            result = create_consistency_review(
                request=CreateConsistencyReviewRequest(**payload),
                _current_user=current_user,
                sql_client=sql_client,
                file_store=file_store,
                repository=repository,
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
) -> dict[str, Any]:
    report = apply_manual_review(task_id, request.decision, request.comment.strip())
    if report is None:
        raise HTTPException(status_code=404, detail={"code": "REVIEW_NOT_FOUND", "message": "比对报告不存在"})
    return {"report": report}


@router.get("/reviews/{task_id}/oa-result")
def get_consistency_oa_result(
    task_id: str,
    _current_user: dict[str, Any] = Depends(require_web_console_user),
    repository=Depends(get_review_repository),
) -> dict[str, Any]:
    """提供给 OA 适配器的回传载荷，不在此接口内主动请求 OA。"""
    report = get_tobacco_report(task_id)
    if report is None:
        try:
            detail = repository.get_qc_review_detail(task_id)
        except Exception:
            detail = None
        if detail is None or detail.get("document_type") != "business_tobacco_consistency":
            raise HTTPException(status_code=404, detail={"code": "REVIEW_NOT_FOUND", "message": "比对结果不存在"})
        comparison = dict(detail.get("comparison") or {})
        source_evidence = dict(detail.get("source_evidence") or {})
        source = dict(source_evidence.get("source") or {})
        report = {
            "id": detail["task_id"],
            "review_mode": comparison.get("review_mode", "standard"),
            "overall_result": "待校验" if detail.get("needs_manual_review") else ("通过" if detail.get("risk_level") == "NONE" else "不通过"),
            "risk_level": detail.get("risk_level"),
            "needs_manual_review": detail.get("needs_manual_review"),
            "unmatched_fields": [rule.get("rule_name") for rule in detail.get("rule_results") or [] if not rule.get("passed")],
            "rule_results": detail.get("rule_results") or [],
            "manual_review": detail.get("manual_review"),
            "source_request_id": source.get("requestid"),
            "compare_time": detail.get("updated_at") or detail.get("created_at"),
        }
    return {
        "callback": {
            "requestid": report.get("source_request_id"),
            "review_task_id": report["id"],
            "review_mode": report.get("review_mode"),
            "review_status": report.get("overall_result"),
            "risk_level": report.get("risk_level"),
            "needs_manual_review": bool(report.get("needs_manual_review")),
            "summary": _callback_summary(report),
            "rule_results": report.get("rule_results") or [],
            "manual_review": report.get("manual_review"),
            "completed_at": report.get("compare_time"),
        }
    }


def _callback_summary(report: dict[str, Any]) -> str:
    if report.get("overall_result") == "通过":
        return "烟草证一致性自动核对通过"
    failed = report.get("unmatched_fields") or []
    return "；".join(str(item) for item in failed) or "烟草证一致性核对待人工复核"


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
            attachments.append({
                "document_role": document.source.document_role,
                "docid": document.source.docid,
                "doc_subject": document.source.doc_subject,
                "file_name": stored_file.file_name,
                "relative_path": stored_file.relative_path,
            })
    for source_file in source_files:
        if source_file.docid in stored_docids:
            continue
        file_name = source_file.real_filename or source_file.docimage_filename
        attachments.append({
            "document_role": source_file.document_role,
            "docid": source_file.docid,
            "doc_subject": source_file.doc_subject,
            "file_name": file_name,
            "relative_path": _demo_attachment_path(source_file.docid) if str(first.store_code or "").upper().startswith("DEMO-") else None,
        })
    attachments.extend({
        "document_role": "selected_attachment",
        "file_name": item.get("file_name"),
        "relative_path": item.get("relative_path"),
    } for item in selected_files if item.get("relative_path"))
    deduplicated = []
    seen = set()
    for attachment in attachments:
        key = (attachment.get("docid"), attachment.get("file_name"), attachment.get("relative_path"))
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


def _demo_attachment_path(docid: int | None) -> str | None:
    return {
        1001: "demo/holder-business-license.pdf",
        1002: "demo/tobacco-license.pdf",
        1003: "demo/store-in-store-agreement.pdf",
    }.get(docid)


def _generate_task_id(store_identifier: str) -> str:
    import hashlib
    import time

    raw = f"tobacco-consistency-{store_identifier}-{time.time_ns()}"
    return f"tc-{hashlib.md5(raw.encode()).hexdigest()[:16]}"
