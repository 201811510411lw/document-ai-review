from dataclasses import dataclass
from datetime import datetime, timedelta
from json import dumps
from typing import Any, Protocol

from app.core.config import settings
from app.integrations.wecom.client import WecomClient
from app.models import ReviewResult


MAX_ATTEMPTS = 3
RETRY_DELAYS_MINUTES = (5, 30)


class WecomNotificationRepository(Protocol):
    def enqueue_wecom_notification(
        self,
        *,
        template: str,
        to_user_ids: list[str],
        recipient_names: list[str],
        message: str,
        task_id: str | None,
        document_type: str | None,
        detail_url: str | None,
        created_at: datetime,
    ) -> dict[str, Any]:
        ...

    def list_due_wecom_notifications(self, now: datetime) -> list[dict[str, Any]]:
        ...

    def mark_wecom_notification_sent(
        self,
        *,
        notification_id: int,
        sent_at: datetime,
    ) -> None:
        ...

    def mark_wecom_notification_retry(
        self,
        *,
        notification_id: int,
        attempts: int,
        error: str,
        next_retry_at: datetime,
        updated_at: datetime,
    ) -> None:
        ...

    def mark_wecom_notification_failed(
        self,
        *,
        notification_id: int,
        attempts: int,
        error: str,
        updated_at: datetime,
    ) -> None:
        ...


@dataclass(frozen=True)
class WecomWorkerResult:
    processed: int
    sent: int
    failed: int
    retried: int


def enqueue_review_notification(
    repository: WecomNotificationRepository,
    review_result: ReviewResult,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    recipients = _reviewer_user_ids()
    if not recipients:
        return None
    if not _should_notify(review_result):
        return None
    created_at = now or datetime.now().astimezone()
    return repository.enqueue_wecom_notification(
        template="business-license-review",
        to_user_ids=recipients,
        recipient_names=recipients,
        message=_review_message(review_result),
        task_id=review_result.task_id,
        document_type=review_result.document_type,
        detail_url=_detail_url(review_result.task_id),
        created_at=created_at,
    )


def run_wecom_notification_worker(
    repository: WecomNotificationRepository,
    *,
    client: WecomClient | None = None,
    now: datetime | None = None,
) -> WecomWorkerResult:
    client = client or WecomClient()
    current_time = now or datetime.now().astimezone()
    due_items = repository.list_due_wecom_notifications(current_time)
    sent = 0
    failed = 0
    retried = 0
    for item in due_items:
        attempts = int(item.get("attempts") or 0) + 1
        try:
            client.send_text_message(
                list(item.get("to_user_ids") or []),
                str(item.get("message") or ""),
            )
            repository.mark_wecom_notification_sent(
                notification_id=int(item["id"]),
                sent_at=current_time,
            )
            sent += 1
        except Exception as error:  # noqa: BLE001 - worker must persist external API failures
            message = str(error)
            if attempts >= MAX_ATTEMPTS:
                repository.mark_wecom_notification_failed(
                    notification_id=int(item["id"]),
                    attempts=attempts,
                    error=message,
                    updated_at=current_time,
                )
                failed += 1
            else:
                repository.mark_wecom_notification_retry(
                    notification_id=int(item["id"]),
                    attempts=attempts,
                    error=message,
                    next_retry_at=_next_retry_at(current_time, attempts),
                    updated_at=current_time,
                )
                retried += 1
    return WecomWorkerResult(
        processed=len(due_items),
        sent=sent,
        failed=failed,
        retried=retried,
    )


def _should_notify(review_result: ReviewResult) -> bool:
    return (
        review_result.document_type == "business_license"
        and (
            review_result.needs_manual_review
            or review_result.risk_level.value == "HIGH"
            or review_result.status.value == "FAILED"
        )
    )


def _reviewer_user_ids() -> list[str]:
    configured = [item.strip() for item in settings.wecom_reviewer_user_ids.split(",") if item.strip()]
    return configured or ["@all"]


def _detail_url(task_id: str) -> str | None:
    base_url = settings.wecom_notification_base_url.strip().rstrip("/")
    if not base_url:
        return None
    return f"{base_url}/reviews/{task_id}"


def _review_message(review_result: ReviewResult) -> str:
    lines = [
        "营业执照审核提醒",
        f"任务：{review_result.task_id}",
        f"状态：{review_result.status.value}",
        f"风险：{review_result.risk_level.value}",
        f"摘要：{review_result.summary}",
    ]
    detail_url = _detail_url(review_result.task_id)
    if detail_url:
        lines.append(f"详情：{detail_url}")
    return "\n".join(lines)


def _next_retry_at(now: datetime, attempts: int) -> datetime:
    index = max(0, attempts - 1)
    delay = RETRY_DELAYS_MINUTES[min(index, len(RETRY_DELAYS_MINUTES) - 1)]
    return now + timedelta(minutes=delay)


def notification_details_json(
    *,
    to_user_ids: list[str],
    recipient_names: list[str],
    detail_url: str | None,
) -> str:
    return dumps(
        {
            "to_user_ids": to_user_ids,
            "recipient_names": recipient_names,
            "detail_url": detail_url,
        },
        ensure_ascii=False,
    )
