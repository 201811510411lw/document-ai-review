"""RPA 验真相关模型（含通用 + 影刀 RPA）。"""

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


# ---------------------------------------------------------------------------
# 影刀 RPA 专用模型
# ---------------------------------------------------------------------------

class YindaoJobStatus(StrEnum):
    """影刀 job 状态枚举"""
    WAITING = "waiting"
    RUNNING = "running"
    FINISH = "finish"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"

    @property
    def is_terminal(self) -> bool:
        return self in (YindaoJobStatus.FINISH, YindaoJobStatus.STOPPED, YindaoJobStatus.ERROR)


class YindaoCallbackPayload(BaseModel):
    """影刀回调请求体"""
    jobUuid: str
    dataType: str = "job"
    status: str = ""
    msg: str = ""
    startTime: str | None = None
    endTime: str | None = None
    robotClientName: str | None = None
    robotName: str | None = None
    result: list[dict[str, Any]] = []

    def get_param(self, name: str) -> str | None:
        """从 result 数组中按 name 提取参数值。"""
        for item in self.result:
            if item.get("name") == name:
                value = item.get("value")
                return str(value) if value is not None else None
        return None

    @property
    def requestid(self) -> str | None:
        return self.get_param("requestid")

    @property
    def verify_status(self) -> str | None:
        return self.get_param("verify_status")

    @property
    def parameter_result(self) -> bool | None:
        value = self.get_param("parameter")
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized in ("true", "1"):
            return True
        if normalized in ("false", "0"):
            return False
        return None

    @property
    def screenshot_url(self) -> str | None:
        return self.get_param("screenshot_url")

    @property
    def error_message(self) -> str | None:
        return self.get_param("error_message") or (self.msg if self.msg else None)


class RpaJobRecord(BaseModel):
    """RPA 任务记录 — 存入 review_result.skill_result.rpa_job_record"""
    job_uuid: str
    certificate_no: str
    store_name: str
    requestid: str = ""
    yindao_status: str = ""
    verification_status: str | None = None
    result_label: str = "验真中..."
    screenshot_url: str | None = None
    error_message: str | None = None
    triggered_at: str = ""
    completed_at: str | None = None
