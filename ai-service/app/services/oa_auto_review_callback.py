import logging
from collections.abc import Callable
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
    store_code: str
    result: dict[str, Any]


class OaAutoReviewCallbackClient(Protocol):
    def send(self, payload: OaAutoReviewCallbackPayload) -> None:
        ...


class OaAutoReviewCallbackError(RuntimeError):
    pass


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

    def send(self, payload: OaAutoReviewCallbackPayload) -> None:
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            started_at = monotonic()
            logger.info(
                "OA callback attempt started: workflow_id=%s requestid=%s "
                "store_code=%s attempt=%s/%s target=%s",
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
                    "OA callback network error: workflow_id=%s requestid=%s "
                    "store_code=%s attempt=%s/%s error_type=%s duration_ms=%s",
                    payload.workflow_id,
                    payload.requestid,
                    payload.store_code,
                    attempt,
                    self._max_attempts,
                    type(error).__name__,
                    _elapsed_milliseconds(started_at),
                )
            else:
                if 200 <= response.status_code < 300:
                    logger.info(
                        "OA callback delivery succeeded: workflow_id=%s requestid=%s "
                        "store_code=%s attempt=%s/%s status_code=%s duration_ms=%s",
                        payload.workflow_id,
                        payload.requestid,
                        payload.store_code,
                        attempt,
                        self._max_attempts,
                        response.status_code,
                        _elapsed_milliseconds(started_at),
                    )
                    return
                if response.status_code not in {408, 429} and response.status_code < 500:
                    logger.warning(
                        "OA callback rejected: workflow_id=%s requestid=%s "
                        "store_code=%s attempt=%s/%s status_code=%s duration_ms=%s",
                        payload.workflow_id,
                        payload.requestid,
                        payload.store_code,
                        attempt,
                        self._max_attempts,
                        response.status_code,
                        _elapsed_milliseconds(started_at),
                    )
                    raise OaAutoReviewCallbackError(
                        f"OA callback rejected payload with HTTP {response.status_code}"
                    )
                last_error = OaAutoReviewCallbackError(
                    f"OA callback returned retryable HTTP {response.status_code}"
                )
                logger.warning(
                    "OA callback retryable response: workflow_id=%s requestid=%s "
                    "store_code=%s attempt=%s/%s status_code=%s duration_ms=%s",
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
            f"OA callback delivery failed after {self._max_attempts} attempts"
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
