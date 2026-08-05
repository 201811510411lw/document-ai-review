from collections.abc import Callable
from time import sleep as default_sleep
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field


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
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._sleep = sleep

    def send(self, payload: OaAutoReviewCallbackPayload) -> None:
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
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
            else:
                if 200 <= response.status_code < 300:
                    return
                if response.status_code not in {408, 429} and response.status_code < 500:
                    raise OaAutoReviewCallbackError(
                        f"OA callback rejected payload with HTTP {response.status_code}"
                    )
                last_error = OaAutoReviewCallbackError(
                    f"OA callback returned retryable HTTP {response.status_code}"
                )

            if attempt < self._max_attempts:
                self._sleep(_retry_delay_seconds(attempt))

        raise OaAutoReviewCallbackError(
            f"OA callback delivery failed after {self._max_attempts} attempts"
        ) from last_error


def _retry_delay_seconds(attempt: int) -> float:
    return (1.0, 5.0)[min(max(attempt - 1, 0), 1)]
