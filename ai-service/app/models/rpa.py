"""RPA 验真相关模型。"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class RpaVerificationStatus(StrEnum):
    PENDING = "PENDING"          # 待验真
    IN_PROGRESS = "IN_PROGRESS"  # 验真中
    AUTHENTIC = "AUTHENTIC"      # 验真通过（真实有效）
    SUSPECTED = "SUSPECTED"      # 疑似伪造（信息不符）
    NOT_FOUND = "NOT_FOUND"      # 未查询到该证照
    ERROR = "ERROR"              # 验真过程出错


_STATUS_LABELS = {
    RpaVerificationStatus.PENDING: "待验真",
    RpaVerificationStatus.IN_PROGRESS: "验真中...",
    RpaVerificationStatus.AUTHENTIC: "官网验真通过",
    RpaVerificationStatus.SUSPECTED: "疑似伪造",
    RpaVerificationStatus.NOT_FOUND: "未查到该证照",
    RpaVerificationStatus.ERROR: "验真失败",
}


def rpa_status_label(status: RpaVerificationStatus | str | None) -> str:
    if status is None:
        return "未验真"
    if isinstance(status, str):
        try:
            status = RpaVerificationStatus(status)
        except ValueError:
            return str(status)
    return _STATUS_LABELS.get(status, str(status))


class RpaVerificationResult(BaseModel):
    task_id: str
    certificate_no: str
    status: RpaVerificationStatus
    verified_at: datetime | None = None
    raw_response: dict[str, Any] = {}
    screenshot_url: str | None = None
    error_message: str | None = None
    attempts: int = 0

    @property
    def result_label(self) -> str:
        return rpa_status_label(self.status)
