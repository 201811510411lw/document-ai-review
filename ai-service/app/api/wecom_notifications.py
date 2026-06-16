from fastapi import APIRouter, Depends, Header, HTTPException
from app.core.config import settings
from app.repositories import build_review_result_repository_from_env
from app.services.wecom_notifications import (
    WecomNotificationRepository,
    run_wecom_notification_worker,
)


router = APIRouter(prefix="/api/v1/wecom/notifications", tags=["wecom"])


def get_wecom_notification_repository() -> WecomNotificationRepository:
    return build_review_result_repository_from_env()


@router.post("/worker")
@router.get("/worker")
def run_worker(
    authorization: str | None = Header(default=None),
    repository: WecomNotificationRepository = Depends(get_wecom_notification_repository),
) -> dict[str, int]:
    _require_worker_access(authorization)
    result = run_wecom_notification_worker(repository)
    return {
        "processed": result.processed,
        "sent": result.sent,
        "failed": result.failed,
        "retried": result.retried,
    }


def _require_worker_access(authorization: str | None) -> None:
    if _is_worker_token(authorization):
        return
    raise HTTPException(
        status_code=403,
        detail={"code": "FORBIDDEN_WECOM_WORKER", "message": "无权触发企业微信通知 worker"},
    )


def _is_worker_token(authorization: str | None) -> bool:
    expected = settings.wecom_worker_token
    if not expected or not authorization:
        return False
    scheme, _, token = authorization.partition(" ")
    return scheme.lower() == "bearer" and token == expected
