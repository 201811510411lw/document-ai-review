"""RPA 验真服务：调用外部 RPA 平台对烟草证进行官网真伪核验。"""

from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

from app.models.rpa import RpaVerificationResult, RpaVerificationStatus


class RpaVerificationClient(Protocol):
    """RPA 验真客户端协议。封装对外部 RPA HTTP API 的调用。"""

    def verify(self, certificate_no: str, store_name: str) -> RpaVerificationResult:
        """同步调用 RPA 平台执行验真，返回验真结果。"""
        ...


class DefaultRpaVerificationClient:
    """默认实现：通过 HTTP POST 调用外部 RPA 平台 API。"""

    def __init__(
        self,
        api_base_url: str,
        api_key: str = "",
        timeout_seconds: int = 60,
    ) -> None:
        self._api_base_url = api_base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds

    def verify(self, certificate_no: str, store_name: str) -> RpaVerificationResult:
        now = datetime.now(tz=timezone.utc)
        if not self._api_base_url:
            return RpaVerificationResult(
                task_id="",
                certificate_no=certificate_no,
                status=RpaVerificationStatus.ERROR,
                verified_at=now,
                raw_response={},
                error_message="RPA 验真未配置 (api_base_url 为空)",
            )

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    f"{self._api_base_url}/api/v1/verify",
                    json={
                        "certificate_no": certificate_no,
                        "store_name": store_name,
                        "timestamp": now.isoformat(),
                    },
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                payload = resp.json()
        except httpx.TimeoutException:
            return RpaVerificationResult(
                task_id="",
                certificate_no=certificate_no,
                status=RpaVerificationStatus.ERROR,
                verified_at=datetime.now(tz=timezone.utc),
                raw_response={},
                error_message="RPA 验真请求超时",
            )
        except Exception as exc:
            return RpaVerificationResult(
                task_id="",
                certificate_no=certificate_no,
                status=RpaVerificationStatus.ERROR,
                verified_at=datetime.now(tz=timezone.utc),
                raw_response={},
                error_message=f"RPA 验真请求失败: {exc}",
            )

        try:
            rpa_status = payload.get("status", "")
            screenshot_url = payload.get("screenshot_url") or None
            # 映射 RPA 平台返回的 status 到内部枚举
            status_map = {
                "AUTHENTIC": RpaVerificationStatus.AUTHENTIC,
                "REAL": RpaVerificationStatus.AUTHENTIC,
                "VALID": RpaVerificationStatus.AUTHENTIC,
                "SUSPECTED": RpaVerificationStatus.SUSPECTED,
                "FAKE": RpaVerificationStatus.SUSPECTED,
                "NOT_FOUND": RpaVerificationStatus.NOT_FOUND,
                "ERROR": RpaVerificationStatus.ERROR,
            }
            mapped = status_map.get(rpa_status.upper(), RpaVerificationStatus.ERROR)
            return RpaVerificationResult(
                task_id="",
                certificate_no=certificate_no,
                status=mapped,
                verified_at=datetime.now(tz=timezone.utc),
                raw_response=payload,
                screenshot_url=screenshot_url,
                error_message=payload.get("error_message") or payload.get("message"),
            )
        except Exception as exc:
            return RpaVerificationResult(
                task_id="",
                certificate_no=certificate_no,
                status=RpaVerificationStatus.ERROR,
                verified_at=datetime.now(tz=timezone.utc),
                raw_response=payload,
                error_message=f"RPA 验真结果解析失败: {exc}",
            )


class RpaVerificationService:
    """RPA 验真编排服务。"""

    def __init__(self, client: RpaVerificationClient) -> None:
        self._client = client

    def verify(
        self,
        task_id: str,
        certificate_no: str,
        store_name: str,
    ) -> RpaVerificationResult:
        """执行验真并返回带 task_id 的结果。"""
        result = self._client.verify(certificate_no, store_name)
        result.task_id = task_id
        result.attempts += 1
        return result

    @staticmethod
    def to_skill_result_dict(result: RpaVerificationResult) -> dict[str, Any]:
        """将验真结果转为可存入 skill_result 的 dict。"""
        return {
            "status": result.status.value,
            "certificate_no": result.certificate_no,
            "verified_at": result.verified_at.isoformat() if result.verified_at else None,
            "screenshot_url": result.screenshot_url,
            "result_label": result.result_label,
            "error_message": result.error_message,
            "attempts": result.attempts,
        }
