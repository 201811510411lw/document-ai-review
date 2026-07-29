"""RPA 验真相关 API。

提供手动触发/查询验真接口，以及影刀 RPA 回调接收接口。
"""

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import require_web_console_user
from app.core.config import settings
from app.models import ReviewResult
from app.models.rpa import YindaoCallbackPayload
from app.repositories import build_review_result_repository_from_env
from app.services.rpa_verification import (
    RpaVerificationService,
    YindaoRpaClient,
)

router = APIRouter(
    prefix="/api/v1/tobacco-license",
    tags=["tobacco-license-rpa"],
)


class RpaVerifyRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=128)
    certificate_no: str = Field(min_length=1, max_length=64)
    store_name: str = Field(default="", max_length=256)
    requestid: str = Field(default="", max_length=64)


def _build_rpa_service() -> RpaVerificationService:
    client = YindaoRpaClient(
        api_base_url=settings.rpa_verification_yindao_base_url,
        access_key_id=settings.rpa_verification_yindao_access_key_id,
        access_key_secret=os.environ.get("RPA_YINDAO_ACCESS_KEY_SECRET", ""),
        robot_uuid=settings.rpa_verification_yindao_robot_uuid,
        account_name=settings.rpa_verification_yindao_account_name,
        run_timeout_seconds=settings.rpa_verification_yindao_run_timeout_seconds,
        wait_timeout_seconds=settings.rpa_verification_yindao_wait_timeout_seconds,
        poll_interval=settings.rpa_verification_yindao_poll_interval,
    )
    return RpaVerificationService(client)


def _update_review_result(
    task_id: str,
    service: RpaVerificationService,
    result: Any,
    raw_yindao: dict[str, Any] | None = None,
) -> None:
    """将验真结果写入 review_result 的 skill_result。"""
    repository = build_review_result_repository_from_env()
    payload = repository.get_by_task_id(task_id)
    if payload is not None:
        skill_result = dict(payload.skill_result or {})
        skill_result["rpa_verification"] = service.to_skill_result_dict(
            result, raw_yindao_response=raw_yindao,
        )
        updated = payload.model_copy(update={"skill_result": skill_result})
        repository.save(updated)


# ------------------------------------------------------------------
# 手动触发验真（同步轮询）
# ------------------------------------------------------------------

@router.post("/rpa-verify")
def trigger_rpa_verification(
    request: RpaVerifyRequest,
    _current_user: dict[str, Any] = Depends(require_web_console_user),
) -> dict[str, Any]:
    """手动触发烟草证 RPA 官网验真（同步等待影刀执行完毕）。"""
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
        requestid=request.requestid,
    )

    # 写入 review_result
    _update_review_result(
        request.task_id,
        service,
        result,
        raw_yindao=result.raw_response if result.raw_response else None,
    )

    return {
        "task_id": result.task_id,
        "status": result.status.value,
        "result_label": result.result_label,
        "verified_at": result.verified_at.isoformat() if result.verified_at else None,
        "screenshot_url": result.screenshot_url,
        "error_message": result.error_message,
        "requestid": request.requestid,
    }


# ------------------------------------------------------------------
# 影刀回调接口（兜底）
# ------------------------------------------------------------------

@router.post("/rpa-verify-callback")
def receive_yindao_callback(
    payload: YindaoCallbackPayload,
) -> dict[str, Any]:
    """影刀 RPA 执行完成后的回调接收接口。

    尝试根据 jobUuid 找到对应的审核任务并写入验真结果。
    主流程通过同步轮询已拿到结果，回调作为兜底防止因超时/进程中断丢失数据。
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        "影刀回调: jobUuid=%s status=%s requestid=%s",
        payload.jobUuid, payload.status, payload.requestid,
    )

    # 通过 jobUuid 查找关联的审核任务
    task_id = RpaVerificationService.lookup_task_id_by_job_uuid(payload.jobUuid)
    if not task_id:
        logger.warning("影刀回调: jobUuid=%s 未找到关联任务（可能未使用同步轮询触发）", payload.jobUuid)
        return {"code": 200, "message": "received, no matching task"}

    # 解析回调结果
    certificate_no = payload.get_param("certificate_no") or ""
    if not certificate_no:
        logger.warning("影刀回调: jobUuid=%s 缺少 certificate_no，无法解析结果", payload.jobUuid)
        return {"code": 200, "message": "received, missing certificate_no"}

    try:
        client = _build_rpa_client_internal()
        service = RpaVerificationService(client)
        result = service.handle_callback(payload, task_id, certificate_no)

        # 写入 review_result
        _update_review_result(
            task_id,
            service,
            result,
            raw_yindao=payload.model_dump(mode="json"),
        )
        logger.info("影刀回调: jobUuid=%s → task_id=%s 处理完成", payload.jobUuid, task_id)
    except Exception as exc:
        logger.error("影刀回调处理失败 jobUuid=%s: %s", payload.jobUuid, exc)

    return {"code": 200, "message": "processed"}


def _build_rpa_client_internal() -> YindaoRpaClient:
    """构造影刀客户端（不依赖 Depends，供回调等非请求上下文使用）。"""
    import os
    return YindaoRpaClient(
        api_base_url=settings.rpa_verification_yindao_base_url,
        access_key_id=settings.rpa_verification_yindao_access_key_id,
        access_key_secret=os.environ.get("RPA_YINDAO_ACCESS_KEY_SECRET", ""),
        robot_uuid=settings.rpa_verification_yindao_robot_uuid,
        account_name=settings.rpa_verification_yindao_account_name,
        run_timeout_seconds=settings.rpa_verification_yindao_run_timeout_seconds,
        wait_timeout_seconds=settings.rpa_verification_yindao_wait_timeout_seconds,
        poll_interval=settings.rpa_verification_yindao_poll_interval,
    )


# ------------------------------------------------------------------
# 查询验真状态
# ------------------------------------------------------------------

@router.get("/rpa-verify/{task_id}")
def get_rpa_verification_status(
    task_id: str,
    _current_user: dict[str, Any] = Depends(require_web_console_user),
) -> dict[str, Any]:
    """查询指定审核任务的 RPA 验真状态（从 review_result 中读取）。"""
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
        "raw_yindao_response": rpa_info.get("raw_yindao_response"),
    }
