import logging
from collections.abc import Callable
from json import dumps as json_dumps
from time import sleep as default_sleep
from time import monotonic
from typing import Any, Protocol
from urllib.parse import ParseResult, urlparse

import httpx
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


class OaAutoReviewCallbackPayload(BaseModel):
    workflow_id: int = Field(gt=0)
    requestid: int = Field(gt=0)
    submission_version: int = Field(default=1, gt=0)
    store_code: str
    result: dict[str, Any]


class OaAutoReviewCallbackClient(Protocol):
    def send(
        self, payload: OaAutoReviewCallbackPayload
    ) -> "OaAutoReviewCallbackDelivery | None":
        ...


class OaAutoReviewCallbackError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        delivery: "OaAutoReviewCallbackDelivery | None" = None,
    ) -> None:
        super().__init__(message)
        self.delivery = delivery


class OaAutoReviewCallbackDelivery(BaseModel):
    target: str
    attempt_count: int = Field(ge=1)
    http_status: int | None = None
    response_body: Any = None
    business_accepted: bool | None = None


class HttpOaAutoReviewCallbackClient:
    def __init__(
        self,
        callback_url: str,
        *,
        timeout_seconds: float = 10.0,
        max_attempts: int = 3,
        sleep: Callable[[float], None] = default_sleep,
    ) -> None:
        parsed = urlparse(callback_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("OA callback URL must be an absolute HTTP(S) URL")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._callback_url = callback_url.strip()
        self._callback_target = _safe_callback_target(parsed)
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._sleep = sleep

    def send(
        self, payload: OaAutoReviewCallbackPayload
    ) -> OaAutoReviewCallbackDelivery:
        last_error: Exception | None = None
        last_delivery: OaAutoReviewCallbackDelivery | None = None
        for attempt in range(1, self._max_attempts + 1):
            started_at = monotonic()
            last_delivery = OaAutoReviewCallbackDelivery(
                target=self._callback_target,
                attempt_count=attempt,
            )
            logger.info(
                "[OA自动审核][回调开始] workflow_id=%s requestid=%s "
                "门店=%s 第%s/%s次 目标=%s",
                payload.workflow_id,
                payload.requestid,
                payload.store_code,
                attempt,
                self._max_attempts,
                self._callback_target,
            )
            try:
                response = httpx.post(
                    self._callback_url,
                    json=payload.model_dump(mode="json"),
                    headers={"Content-Type": "application/json"},
                    timeout=self._timeout_seconds,
                    follow_redirects=False,
                )
            except httpx.RequestError as error:
                last_error = error
                logger.warning(
                    "[OA自动审核][回调网络异常] workflow_id=%s requestid=%s "
                    "门店=%s 第%s/%s次 异常类型=%s 耗时=%sms",
                    payload.workflow_id,
                    payload.requestid,
                    payload.store_code,
                    attempt,
                    self._max_attempts,
                    type(error).__name__,
                    _elapsed_milliseconds(started_at),
                )
            else:
                last_delivery = _delivery_from_response(
                    target=self._callback_target,
                    attempt=attempt,
                    response=response,
                )
                if 200 <= response.status_code < 300:
                    if last_delivery.business_accepted is False:
                        logger.warning(
                            "[OA自动审核][回调业务拒绝] workflow_id=%s requestid=%s "
                            "门店=%s 第%s/%s次 HTTP状态=%s 耗时=%sms",
                            payload.workflow_id,
                            payload.requestid,
                            payload.store_code,
                            attempt,
                            self._max_attempts,
                            response.status_code,
                            _elapsed_milliseconds(started_at),
                        )
                        raise OaAutoReviewCallbackError(
                            "OA callback business response rejected payload",
                            delivery=last_delivery,
                        )
                    logger.info(
                        "[OA自动审核][回调成功] workflow_id=%s requestid=%s "
                        "门店=%s 第%s/%s次 HTTP状态=%s 耗时=%sms",
                        payload.workflow_id,
                        payload.requestid,
                        payload.store_code,
                        attempt,
                        self._max_attempts,
                        response.status_code,
                        _elapsed_milliseconds(started_at),
                    )
                    return last_delivery
                if response.status_code not in {408, 429} and response.status_code < 500:
                    logger.warning(
                        "[OA自动审核][回调被拒绝] workflow_id=%s requestid=%s "
                        "门店=%s 第%s/%s次 HTTP状态=%s 耗时=%sms",
                        payload.workflow_id,
                        payload.requestid,
                        payload.store_code,
                        attempt,
                        self._max_attempts,
                        response.status_code,
                        _elapsed_milliseconds(started_at),
                    )
                    raise OaAutoReviewCallbackError(
                        f"OA callback rejected payload with HTTP {response.status_code}",
                        delivery=last_delivery,
                    )
                last_error = OaAutoReviewCallbackError(
                    f"OA callback returned retryable HTTP {response.status_code}"
                )
                logger.warning(
                    "[OA自动审核][回调可重试失败] workflow_id=%s requestid=%s "
                    "门店=%s 第%s/%s次 HTTP状态=%s 耗时=%sms",
                    payload.workflow_id,
                    payload.requestid,
                    payload.store_code,
                    attempt,
                    self._max_attempts,
                    response.status_code,
                    _elapsed_milliseconds(started_at),
                )

            if attempt < self._max_attempts:
                self._sleep(_retry_delay_seconds(attempt))

        raise OaAutoReviewCallbackError(
            f"OA callback delivery failed after {self._max_attempts} attempts",
            delivery=last_delivery,
        ) from last_error


def _retry_delay_seconds(attempt: int) -> float:
    return (1.0, 5.0)[min(max(attempt - 1, 0), 1)]


def _elapsed_milliseconds(started_at: float) -> int:
    return max(0, round((monotonic() - started_at) * 1000))


def _safe_callback_target(parsed: ParseResult) -> str:
    hostname = parsed.hostname or ""
    if ":" in hostname:
        hostname = f"[{hostname}]"
    port = f":{parsed.port}" if parsed.port is not None else ""
    path = parsed.path or "/"
    return f"{parsed.scheme}://{hostname}{port}{path}"


def _delivery_from_response(
    *,
    target: str,
    attempt: int,
    response: httpx.Response,
) -> OaAutoReviewCallbackDelivery:
    body = _safe_response_body(response)
    return OaAutoReviewCallbackDelivery(
        target=target,
        attempt_count=attempt,
        http_status=response.status_code,
        response_body=body,
        business_accepted=_business_accepted(body),
    )


def _safe_response_body(response: httpx.Response) -> Any:
    if not response.content:
        return None
    try:
        body = _redact_sensitive_values(response.json())
    except ValueError:
        body = response.text
    serialized = (
        body
        if isinstance(body, str)
        else json_dumps(body, ensure_ascii=False, default=str)
    )
    if len(serialized) > 4000:
        return serialized[:4000] + "..."
    return body


def _redact_sensitive_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if any(
                    marker in str(key).lower()
                    for marker in (
                        "authorization",
                        "password",
                        "secret",
                        "token",
                        "appcode",
                        "cookie",
                    )
                )
                else _redact_sensitive_values(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive_values(item) for item in value]
    return value


def _business_accepted(body: Any) -> bool | None:
    if not isinstance(body, dict):
        return None
    success = body.get("success")
    if isinstance(success, bool):
        return success
    code = body.get("code")
    if code is not None:
        normalized_code = str(code).strip().lower()
        if normalized_code in {"0", "200", "success", "ok"}:
            return True
        try:
            if int(normalized_code) >= 400:
                return False
        except ValueError:
            pass
    status = str(body.get("status") or "").strip().lower()
    if status in {"success", "ok", "received", "accepted"}:
        return True
    if status in {"failed", "failure", "error", "rejected"}:
        return False
    return None
