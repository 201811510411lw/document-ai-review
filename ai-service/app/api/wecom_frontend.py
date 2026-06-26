from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.auth import login as api_v1_login
from app.api.auth import me as api_v1_me
from app.api.auth import require_web_console_user
from app.api.auth import LoginRequest as ApiV1LoginRequest
from app.api.business_license_reviews import (
    BusinessLicenseReviewReadRepository,
    get_review_read_repository,
)


auth_router = APIRouter(prefix="/auth", tags=["wecom-frontend-auth"])
api_router = APIRouter(prefix="/api", tags=["wecom-frontend"])


class WecomFrontendLoginRequest(BaseModel):
    code: str = ""
    username: str | None = None
    password: str | None = None


def get_wecom_frontend_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    if authorization == "Bearer demo-token":
        return {"username": "DemoUser", "display_name": "演示用户", "is_admin": True}
    return require_web_console_user(request=request, authorization=authorization)


@auth_router.get("/corp-info")
def corp_info() -> dict[str, str]:
    return {"corp_id": ""}


@auth_router.post("/login")
def login(request: WecomFrontendLoginRequest) -> dict[str, Any]:
    username = request.username or "reviewer"
    password = request.password or "reviewer123"
    payload = api_v1_login(ApiV1LoginRequest(username=username, password=password))
    return {
        "token": payload["access_token"],
        "user": _frontend_user(payload["user"]),
    }


@auth_router.get("/profile")
def profile(current_user: dict[str, Any] = Depends(get_wecom_frontend_user)) -> dict[str, Any]:
    if current_user.get("username") == "DemoUser":
        return _frontend_user(current_user)
    return _frontend_user(api_v1_me(current_user)["user"])


@api_router.get("/dashboard/stats")
def dashboard_stats(
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: BusinessLicenseReviewReadRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    payload = repository.list_business_license_reviews(page=1, page_size=1)
    metrics = payload.get("metrics", {})
    total = int(payload.get("total") or 0)
    return {
        "data": {
            "total": total,
            "valid": max(total - int(metrics.get("high_risk") or 0), 0),
            "expiring": int(metrics.get("pending_manual_review") or 0),
            "expiring_soon": int(metrics.get("pending_manual_review") or 0),
            "expired": int(metrics.get("high_risk") or 0),
            "unknown": 0,
            "batches": 0,
        }
    }


@api_router.get("/dashboard/daily")
def dashboard_daily(
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: BusinessLicenseReviewReadRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    payload = repository.list_business_license_reviews(
        review_status="PENDING_MANUAL_REVIEW",
        page=1,
        page_size=10,
    )
    records = [_frontend_review_record(row) for row in payload.get("items", [])]
    return {
        "data": {
            "date": "",
            "expiring": records,
            "expired": [],
            "report_text": "",
        }
    }


@api_router.get("/dashboard/history")
def dashboard_history(
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: BusinessLicenseReviewReadRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    payload = repository.list_business_license_reviews(page=1, page_size=1)
    total = int(payload.get("total") or 0)
    return {"data": [{"date": "", "total": total, "valid": total, "expiring": 0, "expired": 0}]}


@api_router.get("/review/list")
def review_list(
    review_status: str = Query(default=""),
    keyword: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=1000),
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: BusinessLicenseReviewReadRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    review_filter = _frontend_review_filter(review_status)
    payload = repository.list_business_license_reviews(
        business_name=keyword or None,
        risk_level=review_filter.get("risk_level"),
        review_status=review_filter.get("review_status"),
        page=1,
        page_size=limit,
    )
    stats_payload = repository.list_business_license_reviews(
        business_name=keyword or None,
        page=1,
        page_size=1,
    )
    records = [
        _frontend_review_record(
            row,
            force_status=review_filter.get("force_frontend_status"),
        )
        for row in payload.get("items", [])
    ]
    records = [
        record
        for record in records
        if not review_filter.get("filter_frontend_status")
        or record.get("review_status") == review_filter["frontend_status"]
    ]
    stats = _frontend_review_stats(stats_payload)
    return {"records": records, "stats": stats}


@api_router.get("/review/{task_id}")
def review_detail(
    task_id: str,
    _current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: BusinessLicenseReviewReadRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    snapshot = repository.get_business_license_snapshot(task_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    payload = repository.get_by_task_id(task_id)
    payload_dict = payload.model_dump(mode="json") if payload is not None else None
    return {"record": _frontend_review_detail(snapshot, payload_dict)}


@api_router.post("/review/{task_id}/confirm")
def confirm_review(
    task_id: str,
    request: dict[str, Any] | None = None,
    current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: BusinessLicenseReviewReadRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    snapshot = _submit_review_decision(
        repository=repository,
        task_id=task_id,
        decision="approved",
        comment=str((request or {}).get("comment") or ""),
        current_user=current_user,
    )
    return {"status": "ok", "record": _frontend_review_record(snapshot)}


@api_router.post("/review/{task_id}/flag")
def flag_review(
    task_id: str,
    request: dict[str, Any] | None = None,
    current_user: dict[str, Any] = Depends(get_wecom_frontend_user),
    repository: BusinessLicenseReviewReadRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    snapshot = _submit_review_decision(
        repository=repository,
        task_id=task_id,
        decision="rejected",
        comment=str((request or {}).get("comment") or ""),
        current_user=current_user,
    )
    return {"status": "ok", "record": _frontend_review_record(snapshot)}


@api_router.post("/query")
def query_single() -> dict[str, Any]:
    return {"records": [], "stats": _empty_search_stats()}


@api_router.post("/query/batch")
def query_batch() -> dict[str, Any]:
    return {"records": [], "stats": _empty_search_stats()}


@api_router.post("/query/excel")
def query_excel() -> dict[str, Any]:
    return {"records": [], "stats": _empty_search_stats(), "columns": [], "preview": []}


@api_router.post("/query/download")
def query_download() -> dict[str, Any]:
    return {"status": "empty", "message": "当前后端暂无证照打包下载数据源"}


@api_router.get("/query/recent")
def query_recent() -> dict[str, list[Any]]:
    return {"records": []}


@api_router.get("/admin/notify-users")
def get_notify_users() -> dict[str, list[str]]:
    return {"users": []}


@api_router.put("/admin/notify-users")
def set_notify_users(request: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"status": "ok", "users": (request or {}).get("userIds", [])}


@api_router.post("/admin/check-expiry")
def check_expiry() -> dict[str, str]:
    return {"status": "ok", "message": "当前后端暂无效期检查任务"}


@api_router.get("/records")
def records() -> dict[str, Any]:
    return {"status": "ok", "total": 0, "records": []}


@api_router.delete("/records/{record_id}")
def delete_record(record_id: str) -> dict[str, str]:
    return {"status": "ok", "message": f"记录 {record_id} 已忽略"}


@api_router.get("/tobacco/reports")
def tobacco_reports() -> dict[str, Any]:
    return {"records": [], "stats": {"total": 0, "passed": 0, "failed": 0, "pending": 0}}


@api_router.get("/contract/reports")
def contract_reports() -> dict[str, Any]:
    return {"records": [], "stats": {"total": 0, "高": 0, "中": 0, "低": 0}}


def _submit_review_decision(
    *,
    repository: BusinessLicenseReviewReadRepository,
    task_id: str,
    decision: str,
    comment: str,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    snapshot = repository.manual_review_business_license(
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
    extracted = dict(snapshot.get("extracted_fields") or {})
    normalized = dict(snapshot.get("normalized_fields") or {})
    fields = [
        ("主体名称", "subject_name"),
        ("统一社会信用代码", "credit_code"),
        ("法定代表人", "legal_person"),
        ("有效期开始", "valid_from"),
        ("有效期结束", "valid_to"),
        ("住所", "business_address"),
    ]
    return [
        {
            "field": label,
            "recognized": extracted.get(key) or "",
            "expected": normalized.get(key) or "",
            "match": (extracted.get(key) or "") == (normalized.get(key) or ""),
        }
        for label, key in fields
    ]


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


def _current_review_status_to_frontend(row: dict[str, Any]) -> str | None:
    status = row.get("review_status")
    if status == "MANUAL_REVIEWED":
        if row.get("manual_review_decision") == "rejected":
            return "flagged"
        return "confirmed"
    mapped = {
        "PENDING_MANUAL_REVIEW": "pending",
        "REVIEWED": None,
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


def _match_ratio(row: dict[str, Any]) -> int:
    if row.get("risk_level") == "HIGH":
        return 45
    if row.get("risk_level") == "MEDIUM":
        return 72
    return 96


def _document_type_label(document_type: str | None) -> str:
    return {
        "business_license": "营业执照",
        "food_license": "食品经营许可证",
        "food_production_license": "食品生产许可证",
        "product_report": "产品报告",
        "tobacco_license": "烟草证",
        "business_tobacco_consistency": "营业执照与烟草证一致性",
    }.get(document_type or "", "营业执照")


def _empty_search_stats() -> dict[str, int]:
    return {"found": 0, "expiring": 0, "expired": 0, "missing": 0}
