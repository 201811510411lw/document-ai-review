"""RPA 验真相关 API。提供手动触发和查询验真结果的接口。"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import require_web_console_user
from app.core.config import settings
from app.models import ReviewResult
from app.repositories import build_review_result_repository_from_env
from app.services.rpa_verification import (
    DefaultRpaVerificationClient,
    RpaVerificationService,
)


router = APIRouter(
    prefix="/api/v1/tobacco-license",
    tags=["tobacco-license-rpa"],
)


class RpaVerifyRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=128)
    certificate_no: str = Field(min_length=1, max_length=64)
    store_name: str = Field(default="", max_length=256)


def _build_rpa_service() -> RpaVerificationService:
    client = DefaultRpaVerificationClient(
        api_base_url=settings.rpa_verification_tobacco_api_base_url,
        api_key=settings.rpa_verification_tobacco_api_key,
        timeout_seconds=settings.rpa_verification_tobacco_timeout_seconds,
    )
    return RpaVerificationService(client)


@router.post("/rpa-verify")
def trigger_rpa_verification(
    request: RpaVerifyRequest,
    _current_user: dict[str, Any] = Depends(require_web_console_user),
) -> dict[str, Any]:
    """手动触发烟草证 RPA 官网验真。"""
    if not settings.rpa_verification_tobacco_enabled:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "RPA_VERIFICATION_DISABLED",
                "message": "RPA 验真功能未启用",
            },
        )

    service = _build_rpa_service()
    result = service.verify(
        task_id=request.task_id,
        certificate_no=request.certificate_no,
        store_name=request.store_name,
    )

    # 将验真结果写入 review_result 的 skill_result
    repository = build_review_result_repository_from_env()
    payload = repository.get_by_task_id(request.task_id)
    if payload is not None:
        skill_result = dict(payload.skill_result or {})
        skill_result["rpa_verification"] = service.to_skill_result_dict(result)
        updated = payload.model_copy(update={"skill_result": skill_result})
        repository.save(updated)

    return {
        "task_id": result.task_id,
        "status": result.status.value,
        "result_label": result.result_label,
        "verified_at": result.verified_at.isoformat() if result.verified_at else None,
        "screenshot_url": result.screenshot_url,
        "error_message": result.error_message,
    }


@router.get("/rpa-verify/{task_id}")
def get_rpa_verification_status(
    task_id: str,
    _current_user: dict[str, Any] = Depends(require_web_console_user),
) -> dict[str, Any]:
    """查询指定审核任务的 RPA 验真状态。"""
    repository = build_review_result_repository_from_env()
    payload = repository.get_by_task_id(task_id)
    if payload is None or not isinstance(payload.skill_result, dict):
        return {"task_id": task_id, "status": None, "result_label": "未验真"}

    rpa_info = payload.skill_result.get("rpa_verification")
    if not rpa_info:
        return {"task_id": task_id, "status": None, "result_label": "未验真"}

    from app.models.rpa import rpa_status_label

    return {
        "task_id": task_id,
        "status": rpa_info.get("status"),
        "certificate_no": rpa_info.get("certificate_no"),
        "verified_at": rpa_info.get("verified_at"),
        "screenshot_url": rpa_info.get("screenshot_url"),
        "result_label": rpa_info.get("result_label") or rpa_status_label(rpa_info.get("status")),
        "error_message": rpa_info.get("error_message"),
        "attempts": rpa_info.get("attempts", 0),
    }
