import logging
import os
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.models import (
    AuditEvent,
    ManualReview,
    ManualReviewStatus,
    ReviewInputContext,
    ReviewResult,
    ReviewStatus,
    RiskLevel,
    RuleResult,
)
from app.services.tobacco_consistency_extraction import resolved_consistency_fields
from app.services.rpa_verification import RpaVerificationService, YindaoRpaClient


logger = logging.getLogger(__name__)


def run_tobacco_rpa_precheck(
    *,
    input_context: ReviewInputContext,
    tobacco_result: ReviewResult | None,
    verify: Callable[..., dict | None],
    confirmed_fields: dict[str, Any] | None = None,
) -> ReviewResult | None:
    """先验真；仅返回真实执行结果，负面或技术未完成时终止后续审核。"""
    fields = resolved_consistency_fields(tobacco_result, confirmed_fields or {})
    certificate_no = str(fields.get("license_no") or "").strip()
    if tobacco_result is None or not certificate_no:
        return None
    now = datetime.now(timezone.utc)
    result = tobacco_result.model_copy(deep=True, update={
        "task_id": input_context.task_id,
        "use_case_name": input_context.use_case_name,
        "use_case_version": input_context.use_case_version,
        "skill_name": input_context.use_case_name,
        "skill_version": input_context.use_case_version,
        "ruleset_version": input_context.ruleset_version,
        "document_type": "business_tobacco_consistency",
        "capability_names": ["tobacco_license", "tobacco_license_consistency"],
        "rule_results": [],
        "created_at": now,
        "updated_at": now,
        "skill_result": {
            "tobacco_license_fields": fields,
            "extracted_fields": {"tobacco_license": fields},
            "comparison": {"review_mode": input_context.input.options.get("review_mode", "standard")},
            "source_evidence": {"source": input_context.input.source},
            "document_extraction": {
                "tobacco_license": {
                    "task_id": tobacco_result.task_id,
                    "status": tobacco_result.status.value,
                    "document_type": tobacco_result.document_type,
                    "payload": tobacco_result.model_dump(mode="json"),
                },
            },
        },
    })
    payload = verify(
        result=result,
        task_id=result.task_id,
        certificate_no=certificate_no,
        store_name=input_context.input.supplier_name,
        requestid=str(input_context.input.source.get("requestid") or ""),
    )
    if payload is None:
        return None
    now = datetime.now(timezone.utc)
    result.updated_at = now
    status = str(payload.get("status") or "")
    rejected = status in {"FAILED", "SUSPECTED", "NOT_FOUND"}
    authentic = status == "AUTHENTIC"
    if not rejected and not authentic:
        payload = {**payload, "status": "ERROR", "original_status": status}
    summary = (
        "烟草证官网验真未通过，已停止后续审核" if rejected
        else "烟草证官网验真通过，继续证照一致性审核" if authentic
        else "烟草证官网验真未可靠完成，已停止后续审核"
    )
    result.skill_result["rpa_verification"] = payload
    result.skill_result["consistency_skipped"] = not authentic
    result.skill_result["comparison"]["consistency_skipped"] = not authentic
    result.status = ReviewStatus.REVIEWED if rejected or authentic else ReviewStatus.FAILED
    result.risk_level = RiskLevel.NONE if authentic else RiskLevel.HIGH
    result.needs_manual_review = not (rejected or authentic)
    result.summary = summary
    result.manual_review = ManualReview(
        status=ManualReviewStatus.PENDING if result.needs_manual_review else ManualReviewStatus.NOT_REQUIRED,
        reasons=[summary] if result.needs_manual_review else [],
    )
    result.rule_results = [RuleResult(
        rule_code="TOBACCO_LICENSE_RPA_VERIFICATION",
        rule_name="烟草证官网验真",
        passed=authentic,
        risk_level_on_failure=RiskLevel.HIGH,
        message=summary,
        details={"certificate_no": certificate_no, "rpa_status": payload["status"]},
    )]
    result.audit_events = [AuditEvent(
        event_type="tobacco_license.rpa_precheck.completed",
        message=summary,
        occurred_at=now,
        details={"rpa_status": payload["status"], "consistency_skipped": not authentic},
    )]
    return result


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
