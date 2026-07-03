import csv
import io
import json
import os
import zipfile
from datetime import date, datetime
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx
from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from app.api.auth import me as api_v1_me
from app.api.auth import require_web_console_user
from app.api.business_license_reviews import (
    BusinessLicenseReviewReadRepository,
    get_review_read_repository,
)
from app.services.validation_service import (
    compute_field_coverage,
    compute_match_ratio,
    compute_validation_fields,
    compute_verification_result,
)
from app.workflows.registry import review_graph_registry


auth_router = APIRouter(prefix="/auth", tags=["wecom-frontend-auth"])
api_router = APIRouter(prefix="/api", tags=["wecom-frontend"])


class BatchQueryRequest(BaseModel):
    names: list[str] = []


class FrontendRepository(BusinessLicenseReviewReadRepository):
    def list_qc_reviews(
        self,
        *,
        supplier_name: str | None = None,
        credit_code: str | None = None,
        document_type: str | None = None,
        risk_level: str | None = None,
        review_status: str | None = None,
        needs_manual_review: bool | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        ...

    def get_qc_review_detail(self, task_id: str) -> dict[str, Any] | None:
        ...

    def manual_review_qc_review(
        self,
        *,
        task_id: str,
        decision: str,
        comment: str,
        reviewer_id: str,
        reviewer_username: str,
        reviewed_at: datetime,
    ) -> dict[str, Any] | None:
        ...

    def get_frontend_setting(self, key: str, default: Any = None) -> Any:
        ...

    def set_frontend_setting(self, key: str, value: Any) -> None:
        ...


def get_wecom_frontend_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return require_web_console_user(request=request, authorization=authorization)


@auth_router.get("/profile")
def profile(current_user: dict[str, Any] = Depends(get_wecom_frontend_user)) -> dict[str, Any]:
    return _frontend_user(api_v1_me(current_user)["user"])


@api_router.get("/dashboard/stats")
def dashboard_stats(
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: FrontendRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    payload = repository.list_qc_reviews(page=1, page_size=1)
    records = _all_qc_records(repository)
    metrics = _frontend_record_metrics(records)
    workbench = _frontend_workbench_stats(records)
    total = int(payload.get("total") or 0)
    return {
        "data": {
            "total": total,
            "valid": metrics["valid"],
            "expiring": metrics["expiring"],
            "expiring_soon": metrics["expiring"],
            "expired": metrics["expired"],
            "unknown": metrics["unknown"],
            "pending_manual_review": workbench["pending"],
            "batches": 0,
            "type_distribution": metrics["type_distribution"],
        }
    }


@api_router.get("/dashboard/daily")
def dashboard_daily(
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: FrontendRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    today = date.today()
    yesterday = (today - __import__("datetime").timedelta(days=1)).isoformat()
    # 昨日新增：只查询昨天创建的记录（走 SQL 层面 created_at 过滤）
    yesterday_rows = repository.list_qc_reviews_created_since(yesterday)
    yesterday_records = [_frontend_qc_record(row) for row in yesterday_rows]
    # 全部记录：用于展示当前效期概览
    all_records = _all_qc_records(repository)
    return {
        "data": {
            "date": today.isoformat(),
            "new_uploads": {
                "total": len(yesterday_records),
                "valid": [r for r in yesterday_records if r["expire_status"] == "valid"],
                "expiring": [r for r in yesterday_records if r["expire_status"] == "expiring_soon"],
                "expired": [r for r in yesterday_records if r["expire_status"] == "expired"],
                "unknown": [r for r in yesterday_records if r["expire_status"] == "unknown"],
            },
            "all_records": all_records,
            "report_text": "昨日上传证照效期 + 当前全部记录效期概览",
        }
    }


@api_router.get("/dashboard/history")
def dashboard_history(
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: FrontendRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    records = _all_qc_records(repository)
    metrics = _frontend_record_metrics(records)
    return {
        "data": [
            {
                "date": date.today().isoformat(),
                "total": len(records),
                "valid": metrics["valid"],
                "expiring": metrics["expiring"],
                "expired": metrics["expired"],
            }
        ]
    }


@api_router.get("/review/list")
def review_list(
    review_status: str = Query(default=""),
    keyword: str = Query(default=""),
    document_type: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=1000),
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: FrontendRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    review_filter = _frontend_review_filter(review_status)
    records_scope = _all_qc_records(repository, document_type=_blank_to_none(document_type))
    records = _filter_frontend_records(
        records_scope,
        [keyword.strip()] if keyword.strip() else [],
    )
    records = [
        {**record, "review_status": review_filter.get("force_frontend_status") or record.get("review_status")}
        for record in records
        if _frontend_record_matches_review_filter(record, review_filter)
    ]
    stats = _frontend_workbench_stats(records_scope)
    return {"records": records[:limit], "stats": stats}


@api_router.get("/review/{task_id}")
def review_detail(
    task_id: str,
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: FrontendRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    detail = repository.get_qc_review_detail(task_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    payload = repository.get_by_task_id(task_id)
    payload_dict = payload.model_dump(mode="json") if payload is not None else None
    return {"record": _frontend_qc_detail(detail, payload_dict)}


@api_router.post("/review/{task_id}/confirm")
def confirm_review(
    task_id: str,
    request: dict[str, Any] | None = None,
    current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: FrontendRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    snapshot = _submit_review_decision(
        repository=repository,
        task_id=task_id,
        decision="approved",
        comment=str((request or {}).get("comment") or ""),
        current_user=current_user,
    )
    return {"status": "ok", "record": _frontend_qc_record(snapshot)}


@api_router.post("/review/{task_id}/flag")
def flag_review(
    task_id: str,
    request: dict[str, Any] | None = None,
    current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: FrontendRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    snapshot = _submit_review_decision(
        repository=repository,
        task_id=task_id,
        decision="rejected",
        comment=str((request or {}).get("comment") or ""),
        current_user=current_user,
    )
    return {"status": "ok", "record": _frontend_qc_record(snapshot)}


@api_router.get("/proxy/file")
def proxy_file(
    url: str = Query(..., description="文件直链 URL"),
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
) -> Response:
    """代理下载外部存储文件，解决跨域/HTTPS 混合内容问题。"""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(status_code=400, detail="无效的文件地址")
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "application/octet-stream")
            return Response(content=resp.content, media_type=content_type)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="文件下载超时")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"源站返回 {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件下载失败: {str(e)}")


@api_router.post("/query")
def query_single(
    request: dict[str, Any] | None = None,
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: FrontendRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    keyword = str((request or {}).get("keyword") or "").strip()
    document_type = str((request or {}).get("document_type") or "").strip() or None
    records = _all_qc_records(repository, document_type=document_type)
    records = _filter_frontend_records(records, [keyword] if keyword else [])
    return {"records": records, "stats": _search_stats(records, 1 if keyword else 0)}


@api_router.post("/query/batch")
def query_batch(
    request: BatchQueryRequest,
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: FrontendRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    terms = _normalize_query_terms(request.names)
    records = _filter_frontend_records(_all_qc_records(repository), terms)
    return {"records": records, "stats": _search_stats(records, len(terms))}


@api_router.post("/query/excel")
async def query_excel(
    file: UploadFile = File(...),
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: FrontendRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    content = await file.read()
    parsed = _parse_uploaded_query_table(file.filename or "", content)
    terms = _normalize_query_terms(parsed["terms"])
    records = _filter_frontend_records(_all_qc_records(repository), terms)
    return {
        "records": records,
        "stats": _search_stats(records, len(terms)),
        "columns": parsed["columns"],
        "preview": parsed["preview"],
    }


@api_router.post("/query/download")
def query_download(
    request: dict[str, Any] | None = None,
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: FrontendRepository = Depends(get_review_read_repository),
) -> Response:
    ids = [str(item).strip() for item in (request or {}).get("ids", []) if str(item).strip()]
    selected = [record for record in _all_qc_records(repository) if record["id"] in set(ids)]
    records = [record for record in selected if record.get("source_file_url")]
    missing_attachment_records = [
        {"id": record["id"], "company_name": record["company_name"], "reason": "缺少 source_file_url"}
        for record in selected
        if not record.get("source_file_url")
    ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "records": records,
                    "missing_attachment_records": missing_attachment_records,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        archive.writestr(
            "README.txt",
            "当前 demo 不代理下载外部证照原文件。本压缩包包含可追溯记录和原始文件 URL。",
        )
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="certificates.zip"'},
    )


@api_router.get("/query/recent")
def query_recent(
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: FrontendRepository = Depends(get_review_read_repository),
) -> dict[str, list[Any]]:
    return {"records": _all_qc_records(repository)[:10]}


@api_router.get("/admin/notify-users")
def get_notify_users(
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: FrontendRepository = Depends(get_review_read_repository),
) -> dict[str, list[str]]:
    return {"users": repository.get_frontend_setting("daily_notify_users", [])}


@api_router.put("/admin/notify-users")
def set_notify_users(
    request: dict[str, Any] | None = None,
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: FrontendRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    users = _normalize_user_ids((request or {}).get("userIds") or [])
    repository.set_frontend_setting("daily_notify_users", users)
    return {"status": "ok", "users": users}


@api_router.post("/admin/check-expiry")
def check_expiry(
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: FrontendRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    metrics = _frontend_record_metrics(_all_qc_records(repository))
    return {"status": "ok", "message": "已基于当前审核结果刷新效期统计", "metrics": metrics}


@api_router.get("/records")
def records(
    keyword: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=1000),
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: FrontendRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    ignored_ids = set(repository.get_frontend_setting("ignored_record_ids", []))
    records = [
        record
        for record in _filter_frontend_records(
            _all_qc_records(repository),
            [keyword.strip()] if keyword.strip() else [],
        )
        if record["id"] not in ignored_ids
    ][:limit]
    return {"status": "ok", "total": len(records), "records": records}


@api_router.get("/records/export")
def export_records(
    keyword: str = Query(default=""),
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: FrontendRepository = Depends(get_review_read_repository),
) -> Response:
    ignored_ids = set(repository.get_frontend_setting("ignored_record_ids", []))
    records = [
        record
        for record in _filter_frontend_records(
            _all_qc_records(repository),
            [keyword.strip()] if keyword.strip() else [],
        )
        if record["id"] not in ignored_ids
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["公司名称", "证照类型", "信用代码", "状态", "风险等级", "创建时间", "来源记录"])
    for record in records:
        writer.writerow(
            [
                record.get("company_name") or "",
                record.get("license_type") or "",
                record.get("credit_code") or "",
                record.get("expire_status") or "",
                record.get("risk_level") or "",
                record.get("created_at") or "",
                record.get("source_record_id") or "",
            ]
        )
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="records.csv"'},
    )


@api_router.delete("/records/{record_id}")
def delete_record(
    record_id: str,
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: FrontendRepository = Depends(get_review_read_repository),
) -> dict[str, str]:
    ignored_ids = repository.get_frontend_setting("ignored_record_ids", [])
    if record_id not in ignored_ids:
        ignored_ids.append(record_id)
        repository.set_frontend_setting("ignored_record_ids", ignored_ids)
    return {"status": "ok", "message": f"记录 {record_id} 已从工作台列表忽略"}


@api_router.get("/admin/license-types")
def license_types(
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: FrontendRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    counts = _frontend_record_metrics(_all_qc_records(repository))["document_type_counts"]
    items = []
    for graph in review_graph_registry.list():
        for document_type in graph["supported_document_types"]:
            if document_type in {"contract", "contract_review"}:
                continue
            items.append(
                {
                    "document_type": document_type,
                    "name": _document_type_label(document_type),
                    "use_case_name": graph["name"],
                    "ruleset_version": graph["ruleset_version"],
                    "enabled": True,
                    "readonly": True,
                    "record_count": counts.get(document_type, 0),
                }
            )
    return {"items": items, "readonly": True}


@api_router.post("/admin/import/preview")
async def import_preview(
    file: UploadFile = File(...),
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: FrontendRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    content = await file.read()
    parsed = _parse_uploaded_query_table(file.filename or "", content)
    terms = _normalize_query_terms(parsed["terms"])
    matched = _filter_frontend_records(_all_qc_records(repository), terms)
    return {
        "status": "preview_only",
        "message": "当前批量导入仅做解析预览，不会静默入库或触发审核。",
        "success_count": len(matched),
        "failure_count": max(len(terms) - len(matched), 0),
        "errors": _missing_terms(terms, matched),
        "records": matched,
        "columns": parsed["columns"],
        "preview": parsed["preview"],
    }


@api_router.get("/tobacco/reports")
def tobacco_reports() -> dict[str, Any]:
    return {"records": [], "stats": {"total": 0, "passed": 0, "failed": 0, "pending": 0}}


@api_router.get("/contract/reports")
def contract_reports() -> dict[str, Any]:
    return {"records": [], "stats": {"total": 0, "高": 0, "中": 0, "低": 0}}


def _submit_review_decision(
    *,
    repository: FrontendRepository,
    task_id: str,
    decision: str,
    comment: str,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    snapshot = repository.manual_review_qc_review(
        task_id=task_id,
        decision=decision,
        comment=comment,
        reviewer_id=str(current_user.get("username") or current_user.get("user_id") or "web-console"),
        reviewer_username=str(current_user.get("display_name") or current_user.get("name") or ""),
        reviewed_at=datetime.now().astimezone(),
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return snapshot


def _frontend_user(user: dict[str, Any]) -> dict[str, Any]:
    user_id = str(user.get("username") or user.get("user_id") or "")
    return {
        "user_id": user_id,
        "name": user.get("display_name") or user.get("name") or user_id,
        "is_admin": True,
    }


def _frontend_review_record(
    row: dict[str, Any],
    *,
    force_status: str | None = None,
) -> dict[str, Any]:
    return {
        "id": row.get("task_id"),
        "company_name": row.get("business_name") or row.get("supplier_name") or "未识别主体名称",
        "license_type": _document_type_label(row.get("document_type")),
        "credit_code": row.get("credit_code") or "",
        "expire_date": "",
        "expire_status": _risk_to_expire_status(row.get("risk_level")),
        "expire_days_remaining": None,
        "match_ratio": _match_ratio(row),
        "review_status": force_status or _current_review_status_to_frontend(row),
        "created_at": row.get("created_at") or row.get("updated_at") or "",
        "source_file_url": row.get("source_url") or "",
    }


def _frontend_qc_record(
    row: dict[str, Any],
    *,
    force_status: str | None = None,
) -> dict[str, Any]:
    # ★ 改：优先取 normalized 格式（2024-11-14），再取原始格式（2024年11月14日）
    normalized = row.get("normalized_fields") or {}
    extracted = row.get("extracted_fields") or {}
    valid_to = _first_text(
        normalized.get("valid_to") if isinstance(normalized, dict) else None,
        extracted.get("valid_to") if isinstance(extracted, dict) else None,
        row.get("valid_to"),
    )
    # ★ 无证照文件时，不展示到期相关数据
    if not row.get("source_url"):
        expire_date = ""
        expire_status = "unknown"
        expire_days = None
    else:
        expire_days = _days_remaining(valid_to)
        expire_date = _normalize_date_text(valid_to) if valid_to else ""
        if expire_days is not None:
            if expire_days <= 0:
                expire_status = "expired"
            elif expire_days <= 30:
                expire_status = "expiring_soon"
            else:
                expire_status = "valid"
        else:
            # valid_to 缺失时检查 LLM 有效期规则结果
            rule_results = row.get("rule_results") or []
            validity_passed = any(
                r.get("passed") is True and "VALID" in str(r.get("rule_code", "")).upper()
                for r in rule_results
            )
            if validity_passed:
                expire_status = "valid"
            else:
                expire_status = _risk_to_expire_status(row.get("risk_level"))
    validation_fields = _validation_fields(row)
    product_name = ""
    sample_name = ""
    extracted = row.get("extracted_fields") or {}
    if isinstance(extracted, dict):
        product_name = str(extracted.get("product_name") or extracted.get("sample_name") or "")
        sample_name = str(extracted.get("sample_name") or "")
    return {
        "id": row.get("task_id"),
        "company_name": row.get("supplier_name") or row.get("business_name") or "未识别主体名称",
        "license_type": row.get("document_type_label") or _document_type_label(row.get("document_type")),
        "document_type": row.get("document_type") or "",
        "credit_code": row.get("credit_code") or "",
        "legal_person": row.get("legal_person") or "",
        "expire_date": expire_date,
        "expire_status": expire_status,
        "expire_days_remaining": expire_days,
        "risk_level": row.get("risk_level") or "",
        "risk_level_label": row.get("risk_level_label") or "",
        "match_ratio": _match_ratio(row, validation_fields=validation_fields),
        "field_coverage": compute_field_coverage(validation_fields),
        "verification_result": compute_verification_result(validation_fields),
        "review_status": force_status or _current_review_status_to_frontend(row),
        "created_at": row.get("created_at") or row.get("updated_at") or "",
        "source_file_url": row.get("source_url") or "",
        "source_file_name": _source_file_name(row),
        "source_record_id": row.get("source_record_id") or "",
        "summary": row.get("summary") or "",
        "product_name": product_name,
        "sample_name": sample_name,
    }


def _frontend_qc_detail(detail: dict[str, Any], payload: dict[str, Any] | None) -> dict[str, Any]:
    record = _frontend_qc_record(detail)
    validation_fields = _validation_fields(detail)
    verification_result = compute_verification_result(validation_fields)
    record.update(
        {
            "review_comment": (detail.get("manual_review") or {}).get("comment") or "",
            "match_ratio": _match_ratio(detail, validation_fields=validation_fields),
            "field_coverage": compute_field_coverage(validation_fields),
            "validation_fields": validation_fields,
            "verification_result": verification_result,
            "raw_payload": payload or {},
            "rule_results": detail.get("rule_results") or [],
            "extracted_fields": detail.get("extracted_fields") or {},
            "normalized_fields": detail.get("normalized_fields") or {},
        }
    )
    return record


def _all_qc_records(
    repository: FrontendRepository,
    *,
    document_type: str | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = repository.list_qc_reviews(
            document_type=document_type,
            page=page,
            page_size=100,
        )
        records.extend(_frontend_qc_record(row) for row in payload.get("items", []))
        if page >= int(payload.get("total_pages") or 1):
            break
        page += 1
    return records


def _filter_frontend_records(records: list[dict[str, Any]], terms: list[str]) -> list[dict[str, Any]]:
    if not terms:
        return records
    normalized_terms = [term.lower() for term in terms if term.strip()]
    if not normalized_terms:
        return records
    result = []
    seen = set()
    for record in records:
        haystack = " ".join(
            str(record.get(key) or "")
            for key in (
                "company_name",
                "credit_code",
                "license_type",
                "document_type",
                "source_record_id",
                "summary",
                "product_name",
                "sample_name",
            )
        ).lower()
        if any(term in haystack for term in normalized_terms) and record["id"] not in seen:
            result.append(record)
            seen.add(record["id"])
    return result


def _frontend_record_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    type_counts: dict[str, int] = {}
    type_distribution: list[dict[str, Any]] = []
    for record in records:
        document_type = record.get("document_type") or "unknown"
        type_counts[document_type] = type_counts.get(document_type, 0) + 1
    colors = ["#2f6f6d", "#8b5e3c", "#4f6f9f", "#b65f7a", "#6b7280", "#7c6a43"]
    for index, (document_type, count) in enumerate(type_counts.items()):
        type_distribution.append(
            {
                "type": _document_type_label(document_type),
                "document_type": document_type,
                "count": count,
                "color": colors[index % len(colors)],
            }
        )
    return {
        "valid": sum(1 for row in records if row["expire_status"] == "valid"),
        "expiring": sum(1 for row in records if row["expire_status"] == "expiring_soon"),
        "expired": sum(1 for row in records if row["expire_status"] == "expired"),
        "unknown": sum(1 for row in records if row["expire_status"] == "unknown"),
        "document_type_counts": type_counts,
        "type_distribution": type_distribution,
    }


def _frontend_workbench_stats(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(records),
        "pending": sum(1 for row in records if row.get("review_status") == "pending"),
        "confirmed": sum(1 for row in records if row.get("review_status") != "pending"),
        "flagged": sum(
            1
            for row in records
            if row.get("review_status") == "flagged" or row.get("risk_level") == "HIGH"
        ),
    }


def _frontend_record_matches_review_filter(record: dict[str, Any], review_filter: dict[str, str]) -> bool:
    if not review_filter:
        return True
    if review_filter.get("risk_level") and record.get("risk_level") != review_filter["risk_level"]:
        return False
    if review_filter.get("force_frontend_status"):
        return True
    frontend_status = review_filter.get("frontend_status")
    if frontend_status and record.get("review_status") != frontend_status:
        return False
    return True


def _frontend_review_detail(snapshot: dict[str, Any], payload: dict[str, Any] | None) -> dict[str, Any]:
    record = _frontend_review_record(snapshot)
    record.update(
        {
            "id": snapshot.get("task_id"),
            "source_file_url": snapshot.get("source_url") or "",
            "review_comment": snapshot.get("manual_review_comment") or "",
            "validation_fields": _validation_fields(snapshot),
            "raw_payload": payload or {},
        }
    )
    return record


def _validation_fields(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return compute_validation_fields(snapshot, snapshot.get("document_type") or "")


def _recognized_field_value(
    extracted: dict[str, Any],
    normalized: dict[str, Any],
    keys: tuple[str, ...],
) -> Any:
    if _is_date_field(keys):
        normalized_value = _first_field_value(normalized, keys)
        if normalized_value is not None:
            return normalized_value
    return _first_field_value(extracted, keys)


def _validation_field_risk(keys: tuple[str, ...], recognized: Any) -> str:
    if "valid_to" in keys:
        return _valid_to_status(recognized)
    return ""


def _source_validation_fields(snapshot: dict[str, Any]) -> dict[str, Any]:
    source_evidence = dict(snapshot.get("source_evidence") or {})
    source = source_evidence.get("source") if isinstance(source_evidence.get("source"), dict) else {}
    return {
        "subject_name": source_evidence.get("supplier_name"),
        "producer_name": source_evidence.get("supplier_name"),
        "entrusting_party": source_evidence.get("supplier_name"),
        "manufacturer_name": source_evidence.get("supplier_name"),
        "credit_code": _source_credit_code(source_evidence, source),
    }


def _requires_source_field(keys: tuple[str, ...]) -> bool:
    return any(
        key in {"subject_name", "producer_name", "entrusting_party", "manufacturer_name", "credit_code"}
        for key in keys
    )


def _is_required_validation_field(
    document_type: str | None,
    keys: tuple[str, ...],
) -> bool:
    if document_type == "food_production_license":
        required_keys = {
            "producer_name",
            "credit_code",
            "license_no",
            "production_address",
            "legal_person",
            "food_categories",
            "valid_to",
        }
        return any(key in required_keys for key in keys)
    if document_type == "food_license":
        required_keys = {
            "subject_name",
            "credit_code",
            "license_no",
            "business_address",
            "legal_person",
            "business_items",
            "valid_to",
        }
        return any(key in required_keys for key in keys)
    if document_type == "product_report":
        required_keys = {
            "report_no",
            "product_name",
            "sample_name",
            "entrusting_party",
            "manufacturer_name",
            "batch_no",
            "production_date",
            "issue_date",
            "approval_date",
            "valid_to",
            "inspection_conclusion",
        }
        return any(key in required_keys for key in keys)
    return False


def _source_credit_code(source_evidence: dict[str, Any], source: dict[str, Any]) -> str:
    candidates = [
        source_evidence.get("supplier_credit_code"),
        source.get("supplier_credit_code"),
    ]
    source_payload = source.get("source_payload")
    if isinstance(source_payload, dict):
        candidates.extend(
            [
                source_payload.get("creditCode"),
                source_payload.get("credit_code"),
                source_payload.get("unifiedSocialCreditCode"),
                source_payload.get("socialCreditCode"),
                source_payload.get("num"),
                source_payload.get("t1.num"),
            ]
        )
    for candidate in candidates:
        normalized = _normalize_credit_code_candidate(candidate)
        if normalized:
            return normalized
    return ""


def _normalize_credit_code_candidate(value: Any) -> str:
    text = "".join(str(value or "").split()).upper()
    return text if len(text) in {15, 18} else ""


def _validation_field_specs(document_type: str | None) -> list[tuple[str, tuple[str, ...]]]:
    if document_type == "food_license":
        return [
            ("经营者名称", ("subject_name",)),
            ("统一社会信用代码", ("credit_code",)),
            ("许可证编号", ("license_no",)),
            ("经营场所", ("business_address",)),
            ("法定代表人/负责人", ("legal_person",)),
            ("经营项目", ("business_items",)),
            ("有效期开始", ("valid_from",)),
            ("有效期结束", ("valid_to",)),
            ("发证机关", ("issue_authority",)),
            ("签发日期", ("issue_date",)),
        ]
    if document_type == "food_production_license":
        return [
            ("生产者名称", ("producer_name",)),
            ("统一社会信用代码", ("credit_code",)),
            ("许可证编号", ("license_no",)),
            ("生产地址", ("production_address",)),
            ("法定代表人/负责人", ("legal_person",)),
            ("食品类别", ("food_categories",)),
            ("有效期开始", ("valid_from",)),
            ("有效期结束", ("valid_to",)),
            ("发证机关", ("issue_authority",)),
            ("签发日期", ("issue_date",)),
        ]
    if document_type == "product_report":
        return [
            ("报告编号", ("report_no",)),
            ("样品名称", ("sample_name", "product_name")),
            ("委托单位", ("entrusting_party", "vendor_name_extracted")),
            ("生产商", ("manufacturer_name",)),
            ("批号", ("batch_no",)),
            ("生产日期", ("production_date",)),
            ("签发日期", ("issue_date", "sign_date")),
            ("批准日期", ("approval_date",)),
            ("有效截止日", ("valid_to",)),
            ("检验结论", ("inspection_conclusion", "inspection_result")),
        ]
    return [
        ("主体名称", ("subject_name",)),
        ("统一社会信用代码", ("credit_code",)),
        ("法定代表人", ("legal_person",)),
        ("有效期开始", ("valid_from", "established_date", "issue_date")),
        ("有效期结束", ("valid_to",)),
        ("住所", ("business_address",)),
    ]


def _first_field_value(fields: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = fields.get(key)
        if _display_field_value(value):
            return value
    return None


def _display_field_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "、".join(_display_field_value(item) for item in value if _display_field_value(item))
    if isinstance(value, dict):
        return "、".join(
            _display_field_value(item)
            for item in value.values()
            if _display_field_value(item)
        )
    return str(value).strip()


def _field_values_match(
    document_type: str | None,
    keys: tuple[str, ...],
    recognized: Any,
    expected: Any,
) -> bool:
    if "valid_to" in keys:
        validity = _valid_to_status(recognized)
        if validity in {"expired", "expiring_soon", "invalid"}:
            return False
    if _is_date_field(keys):
        return _normalize_date_text(recognized) == _normalize_date_text(expected)
    if any(key in {"subject_name", "producer_name", "entrusting_party", "manufacturer_name"} for key in keys):
        return _normalize_business_subject_name(recognized) == _normalize_business_subject_name(expected)
    return _display_field_value(recognized) == _display_field_value(expected)


def _is_date_field(keys: tuple[str, ...]) -> bool:
    return any(
        key in {
            "valid_from",
            "valid_to",
            "issue_date",
            "sign_date",
            "approval_date",
            "production_date",
            "established_date",
        }
        for key in keys
    )


def _normalize_date_text(value: Any) -> str:
    text = _display_field_value(value)
    if not text:
        return ""
    normalized = text.strip()
    for suffix in ("日", "号"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
    normalized = normalized.replace("年", "-").replace("月", "-").replace("/", "-").replace(".", "-")
    parts = [part for part in normalized.split("-") if part]
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        year, month, day = parts
        if len(year) == 4:
            return f"{year}-{int(month):02d}-{int(day):02d}"
    return text


def _valid_to_status(value: Any) -> str:
    normalized = _normalize_date_text(value)
    if not normalized:
        return "unknown"
    if "长期" in normalized:
        return "valid"
    from datetime import date

    try:
        days = (date.fromisoformat(normalized) - date.today()).days
    except ValueError:
        return "invalid"
    if days < 0:
        return "expired"
    if days <= 30:
        return "expiring_soon"
    return "valid"


def _normalize_business_subject_name(value: Any) -> str:
    text = _display_field_value(value)
    punctuation = set("()（）[]【】,，.。;；:：-—_·'\"“”‘’")
    return "".join(character for character in text if character not in punctuation)


def _frontend_review_stats(payload: dict[str, Any]) -> dict[str, int]:
    metrics = payload.get("metrics", {})
    total = int(payload.get("total") or 0)
    pending = int(metrics.get("pending_manual_review") or 0)
    return {
        "total": total,
        "pending": pending,
        "confirmed": max(total - pending, 0),
        "flagged": int(metrics.get("high_risk") or 0),
    }


def _frontend_review_filter(status: str) -> dict[str, str]:
    return {
        "pending": {"review_status": "PENDING_MANUAL_REVIEW", "frontend_status": "pending"},
        "confirmed": {
            "review_status": "MANUAL_REVIEWED",
            "frontend_status": "confirmed",
            "filter_frontend_status": "1",
        },
        "flagged": {
            "risk_level": "HIGH",
            "frontend_status": "flagged",
            "force_frontend_status": "flagged",
        },
    }.get(status or "", {})


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _current_review_status_to_frontend(row: dict[str, Any]) -> str | None:
    status = row.get("review_status")
    if status == "MANUAL_REVIEWED":
        if row.get("manual_review_decision") == "rejected":
            return "flagged"
        return "confirmed"
    mapped = {
        "PENDING_MANUAL_REVIEW": "pending",
        "REVIEWED": "confirmed",
        "FAILED": "flagged",
    }
    if row.get("risk_level") == "HIGH" and status != "PENDING_MANUAL_REVIEW":
        return "flagged"
    return mapped.get(status or "", None)


def _risk_to_expire_status(risk_level: str | None) -> str:
    if risk_level == "HIGH":
        return "expired"
    if risk_level == "MEDIUM":
        return "expiring_soon"
    return "valid"


def _match_ratio(
    row: dict[str, Any],
    *,
    validation_fields: list[dict[str, Any]] | None = None,
) -> int:
    fields = validation_fields or compute_validation_fields(row, row.get("document_type") or "")
    return compute_match_ratio(fields, row.get("risk_level") or "")


def _risk_to_match_ratio(risk_level: str | None) -> int:
    if risk_level == "HIGH":
        return 45
    if risk_level == "MEDIUM":
        return 72
    if risk_level == "LOW":
        return 96
    return 96


def _document_type_label(document_type: str | None) -> str:
    return {
        "business_license": "营业执照",
        "food_license": "食品经营许可证",
        "food_production_license": "食品生产许可证",
        "product_report": "商品报告",
        "tobacco_license": "烟草证",
        "business_tobacco_consistency": "营业执照与烟草证一致性",
    }.get(document_type or "", "营业执照")


def _empty_search_stats() -> dict[str, int]:
    return {"found": 0, "expiring": 0, "expired": 0, "missing": 0}


def _search_stats(records: list[dict[str, Any]], requested_count: int) -> dict[str, int]:
    found = len(records)
    return {
        "found": found,
        "expiring": sum(1 for row in records if row["expire_status"] == "expiring_soon"),
        "expired": sum(1 for row in records if row["expire_status"] == "expired"),
        "missing": max(requested_count - found, 0),
    }


def _normalize_query_terms(values: list[Any]) -> list[str]:
    normalized: list[str] = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return normalized


def _normalize_user_ids(values: list[Any]) -> list[str]:
    users: list[str] = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        users.append(text)
        seen.add(text)
    return users


def _parse_uploaded_query_table(filename: str, content: bytes) -> dict[str, Any]:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix == "csv":
        text = content.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
    elif suffix == "xlsx":
        rows = _parse_simple_xlsx(content)
    elif suffix == "xls":
        raise HTTPException(
            status_code=400,
            detail={"code": "UNSUPPORTED_XLS", "message": "当前 demo 支持 CSV 和 XLSX，不支持旧版 XLS"},
        )
    else:
        text = content.decode("utf-8-sig", errors="ignore")
        rows = list(csv.reader(io.StringIO(text)))
    rows = [[str(cell or "").strip() for cell in row] for row in rows if any(str(cell or "").strip() for cell in row)]
    if not rows:
        raise HTTPException(
            status_code=400,
            detail={"code": "EMPTY_QUERY_FILE", "message": "上传文件为空，未找到可查询数据"},
        )
    header = rows[0]
    data_rows = rows[1:] if len(rows) > 1 else []
    column_index = _guess_query_column(header, data_rows)
    terms = [row[column_index] for row in data_rows if len(row) > column_index and row[column_index]]
    if not terms:
        raise HTTPException(
            status_code=400,
            detail={"code": "MISSING_QUERY_COLUMN", "message": "上传文件缺少可查询的公司名称、供应商名称或信用代码列"},
        )
    return {
        "terms": terms,
        "columns": [{"name": name or f"列 {index + 1}", "index": index} for index, name in enumerate(header)],
        "preview": [",".join(row) for row in rows[:5]],
    }


def _parse_simple_xlsx(content: bytes) -> list[list[str]]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as workbook:
            shared_strings = _xlsx_shared_strings(workbook)
            sheet_name = "xl/worksheets/sheet1.xml"
            if sheet_name not in workbook.namelist():
                sheet_name = next(name for name in workbook.namelist() if name.startswith("xl/worksheets/sheet"))
            root = ElementTree.fromstring(workbook.read(sheet_name))
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_XLSX", "message": "无法解析上传的 XLSX 文件"},
        ) from error
    rows: list[list[str]] = []
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    for row_node in root.iter(f"{namespace}row"):
        row_values: list[str] = []
        for cell in row_node.iter(f"{namespace}c"):
            cell_type = cell.attrib.get("t")
            value_node = cell.find(f"{namespace}v")
            inline_node = cell.find(f"{namespace}is/{namespace}t")
            value = ""
            if cell_type == "s" and value_node is not None:
                index = int(value_node.text or "0")
                value = shared_strings[index] if index < len(shared_strings) else ""
            elif inline_node is not None:
                value = inline_node.text or ""
            elif value_node is not None:
                value = value_node.text or ""
            row_values.append(value)
        rows.append(row_values)
    return rows


def _xlsx_shared_strings(workbook: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
    values = []
    for item in root.iter(f"{namespace}si"):
        values.append("".join(node.text or "" for node in item.iter(f"{namespace}t")))
    return values


def _guess_query_column(header: list[str], rows: list[list[str]]) -> int:
    for index, name in enumerate(header):
        if any(keyword in name for keyword in ("公司", "供应商", "名称", "信用代码", "编码")):
            return index
    scores = []
    for index in range(max((len(row) for row in rows), default=len(header))):
        scores.append(sum(1 for row in rows if len(row) > index and row[index]))
    if not scores:
        return 0
    return max(range(len(scores)), key=lambda index: scores[index])


def _missing_terms(terms: list[str], records: list[dict[str, Any]]) -> list[dict[str, str]]:
    found_text = " ".join(
        " ".join(str(record.get(key) or "") for key in ("company_name", "credit_code", "source_record_id"))
        for record in records
    ).lower()
    return [
        {"value": term, "reason": "当前审核结果中未找到匹配记录"}
        for term in terms
        if term.lower() not in found_text
    ]


def _days_remaining(valid_to: str | None) -> int | None:
    if not valid_to:
        return None
    # 支持中文日期格式（如 2024年11月14日）和标准格式（2024-11-14）
    # 长期、永久、无固定期限 → 返回大正数表示长期有效
    text = str(valid_to).strip()
    if any(kw in text for kw in ("长期", "永久", "无固定期限", "2099")):
        return 9999
    normalized = _normalize_date_text(text)
    if not normalized:
        return None
    try:
        end_date = date.fromisoformat(normalized[:10])
    except ValueError:
        return None
    return (end_date - date.today()).days


def _source_file_name(row: dict[str, Any]) -> str:
    source_url = str(row.get("source_url") or "")
    if "/" in source_url:
        return source_url.rsplit("/", 1)[-1] or "证照文件"
    return "证照文件"


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
