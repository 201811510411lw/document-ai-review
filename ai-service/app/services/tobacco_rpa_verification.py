import logging
import os

from app.core.config import settings
from app.models import ReviewResult
from app.services.rpa_verification import RpaVerificationService, YindaoRpaClient


logger = logging.getLogger(__name__)


def execute_tobacco_rpa_verification(
    *,
    result: ReviewResult,
    task_id: str,
    certificate_no: str,
    store_name: str,
    requestid: str,
) -> dict | None:
    """执行可选 RPA 并只更新内存结果；持久化由应用服务统一完成。"""
    if not settings.rpa_verification_tobacco_enabled:
        return None

    try:
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
        service = RpaVerificationService(client)
        verification = service.verify(
            task_id=task_id,
            certificate_no=certificate_no,
            store_name=store_name,
            requestid=requestid,
        )
        payload = service.to_skill_result_dict(
            verification,
            raw_yindao_response=(
                verification.raw_response if verification.raw_response else None
            ),
        )
    except Exception as error:
        logger.warning("RPA 验真异常: %s", error)
        payload = {
            "status": "ERROR",
            "error_message": f"{type(error).__name__}: {error}",
        }

    if isinstance(result.skill_result, dict):
        result.skill_result["rpa_verification"] = payload
    return payload
