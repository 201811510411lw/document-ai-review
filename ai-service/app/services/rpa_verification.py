"""影刀 RPA 验真服务：通过影刀开放平台 OpenAPI 触发烟草证官网真伪核验。"""

import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.models.rpa import (
    RpaJobRecord,
    RpaVerificationResult,
    RpaVerificationStatus,
    YindaoCallbackPayload,
    YindaoJobStatus,
)

logger = logging.getLogger(__name__)

# 影刀开放平台 API 路径（可按实际部署环境调整）
TOKEN_PATH = "/oapi/token/v2/token/create"
START_JOB_PATH = "/oapi/dispatch/v2/job/start"
QUERY_JOB_PATH = "/oapi/dispatch/v2/job/query"


class YindaoRpaClient:
    """影刀 RPA 验真客户端。

    内部流程：
      1. 获取影刀 access_token
      2. 调用 Start Job API 触发 RPA 流程，得到 jobUuid
      3. 轮询 Query Job API 等待任务完成（finish / error）
      4. 将影刀结果映射为内部 RpaVerificationResult

    同步对外接口 verify() 封装了以上全过程。
    """

    def __init__(
        self,
        api_base_url: str,
        access_key_id: str,
        access_key_secret: str,
        robot_uuid: str,
        account_name: str = "",
        robot_client_group_uuid: str = "",
        run_timeout_seconds: int = 300,
        wait_timeout_seconds: int = 600,
        poll_interval: float = 3.0,
    ) -> None:
        self._base_url = api_base_url.rstrip("/")
        self._access_key_id = access_key_id
        self._access_key_secret = access_key_secret
        self._robot_uuid = robot_uuid
        self._account_name = account_name
        self._group_uuid = robot_client_group_uuid
        self._run_timeout = run_timeout_seconds
        self._wait_timeout = wait_timeout_seconds
        self._poll_interval = poll_interval

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def verify(
        self,
        certificate_no: str,
        store_name: str,
        requestid: str = "",
    ) -> RpaVerificationResult:
        """触发影刀 RPA 并轮询等待结果（同步调用）。"""
        try:
            token = self._get_token()
        except Exception as exc:
            return self._error_result(certificate_no, f"获取影刀 token 失败: {exc}")

        try:
            job_uuid = self._start_job(token, certificate_no, store_name, requestid)
        except Exception as exc:
            return self._error_result(certificate_no, f"触发影刀 RPA 失败: {exc}")

        try:
            raw = self._poll_job(job_uuid, timeout=self._run_timeout)
        except TimeoutError:
            return self._error_result(
                certificate_no,
                f"影刀 RPA 执行超时（{self._run_timeout}s）",
                raw_response={"jobUuid": job_uuid},
            )
        except Exception as exc:
            return self._error_result(
                certificate_no,
                f"查询影刀 RPA 结果失败: {exc}",
                raw_response={"jobUuid": job_uuid},
            )

        # 确保 raw_response 中包含 jobUuid，供回调匹配使用
        if isinstance(raw, dict) and "jobUuid" not in raw:
            raw["jobUuid"] = job_uuid
        return self._map_result(certificate_no, job_uuid, raw)

    def parse_callback(
        self,
        payload: YindaoCallbackPayload,
        certificate_no: str,
    ) -> RpaVerificationResult:
        """解析影刀回调结果 → 转为内部结果。"""
        yindao_status = YindaoJobStatus(payload.status) if payload.status else None
        mapped = self._map_yindao_status(yindao_status, payload)
        return RpaVerificationResult(
            task_id="",
            certificate_no=certificate_no,
            status=mapped,
            verified_at=_parse_iso_or_now(payload.endTime),
            raw_response=payload.model_dump(mode="json"),
            screenshot_url=payload.screenshot_url,
            error_message=payload.error_message,
            attempts=1,
        )

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _get_token(self) -> str:
        """获取影刀 access_token。"""
        url = f"{self._base_url}{TOKEN_PATH}"
        resp = httpx.get(
            url,
            params={
                "accessKeyId": self._access_key_id,
                "accessKeySecret": self._access_key_secret,
            },
            timeout=10,
        )
        resp.raise_for_status()
        body = resp.json()
        if not body.get("success"):
            raise RuntimeError(f"影刀 token 接口返回失败: {body}")
        token: str = body["data"]["accessToken"]
        return token

    def _start_job(
        self,
        token: str,
        certificate_no: str,
        store_name: str,
        requestid: str = "",
    ) -> str:
        """触发影刀 RPA 流程，返回 jobUuid。"""
        url = f"{self._base_url}{START_JOB_PATH}"
        params: list[dict[str, str]] = [
            {"name": "certificate_no", "value": certificate_no, "type": "String"},
            {"name": "store_name", "value": store_name, "type": "String"},
        ]
        if requestid:
            params.append({"name": "requestid", "value": requestid, "type": "String"})

        body: dict[str, Any] = {
            "robotUuid": self._robot_uuid,
            "params": params,
            "waitTimeoutSeconds": self._wait_timeout,
            "runTimeout": self._run_timeout,
            "priority": "middle",
        }
        if self._account_name:
            body["accountName"] = self._account_name
        if self._group_uuid:
            body["robotClientGroupUuid"] = self._group_uuid

        resp = httpx.post(
            url,
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json()
        job_uuid: str = result["jobUuid"]
        return job_uuid

    def _query_job(self, token: str, job_uuid: str) -> dict[str, Any]:
        """查询影刀任务状态。"""
        url = f"{self._base_url}{QUERY_JOB_PATH}"
        resp = httpx.get(
            url,
            params={"jobUuid": job_uuid},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def _poll_job(self, job_uuid: str, timeout: int) -> dict[str, Any]:
        """轮询等待影刀任务完成，返回最终结果。"""
        token = self._get_token()
        deadline = time.time() + timeout
        last_raw: dict[str, Any] = {}
        while time.time() < deadline:
            try:
                raw = self._query_job(token, job_uuid)
                last_raw = raw
            except Exception as exc:
                logger.warning("影刀查询失败（继续轮询）: %s", exc)
                time.sleep(self._poll_interval)
                continue

            status_str = raw.get("status", "")
            try:
                yindao_status = YindaoJobStatus(status_str)
            except ValueError:
                yindao_status = YindaoJobStatus.RUNNING

            if yindao_status.is_terminal:
                return raw

            time.sleep(self._poll_interval)

        # 超时
        raise TimeoutError(f"影刀任务 {job_uuid} 超时（{timeout}s）")

    def _map_result(
        self,
        certificate_no: str,
        job_uuid: str,
        raw: dict[str, Any],
    ) -> RpaVerificationResult:
        """将影刀查询结果映射为内部结果。"""
        status_str = raw.get("status", "")
        yindao_status = YindaoJobStatus(status_str) if status_str else None

        # 如果影刀的 result 数组里有验真结果，构造成 callback 模型来解析
        callback = YindaoCallbackPayload(
            jobUuid=job_uuid,
            status=status_str,
            msg=raw.get("msg", ""),
            startTime=raw.get("startTime"),
            endTime=raw.get("endTime"),
            result=raw.get("result", []),
        )

        mapped = self._map_yindao_status(yindao_status, callback)
        return RpaVerificationResult(
            task_id="",
            certificate_no=certificate_no,
            status=mapped,
            verified_at=_parse_iso_or_now(callback.endTime),
            raw_response=raw,
            screenshot_url=callback.screenshot_url,
            error_message=callback.error_message,
            attempts=1,
        )

    @staticmethod
    def _map_yindao_status(
        yindao_status: YindaoJobStatus | None,
        callback: YindaoCallbackPayload,
    ) -> RpaVerificationStatus:
        """影刀 job status → 我方验真状态。"""
        if yindao_status is None:
            return RpaVerificationStatus.ERROR
        if yindao_status == YindaoJobStatus.ERROR:
            return RpaVerificationStatus.ERROR
        if yindao_status == YindaoJobStatus.STOPPED:
            return RpaVerificationStatus.ERROR
        if yindao_status == YindaoJobStatus.FINISH:
            # 从 RPA 输出中读取 verify_status
            vs = callback.verify_status
            if vs == "AUTHENTIC":
                return RpaVerificationStatus.AUTHENTIC
            if vs == "SUSPECTED":
                return RpaVerificationStatus.SUSPECTED
            if vs == "NOT_FOUND":
                return RpaVerificationStatus.NOT_FOUND
            # RPA 完成了但没有有效验真结论
            return RpaVerificationStatus.ERROR
        # waiting / running 不应在终态出现
        return RpaVerificationStatus.ERROR

    @staticmethod
    def _error_result(
        certificate_no: str,
        message: str,
        raw_response: dict[str, Any] | None = None,
    ) -> RpaVerificationResult:
        return RpaVerificationResult(
            task_id="",
            certificate_no=certificate_no,
            status=RpaVerificationStatus.ERROR,
            verified_at=datetime.now(tz=timezone.utc),
            raw_response=raw_response or {},
            error_message=message,
        )


# -----------------------------------------------------------------------
# 编排服务
# -----------------------------------------------------------------------

# jobUuid → task_id 映射，供回调时查找匹配的审核任务
_job_task_map: dict[str, str] = {}


class RpaVerificationService:
    """RPA 验真编排服务。"""

    def __init__(self, client: YindaoRpaClient) -> None:
        self._client = client

    def verify(
        self,
        task_id: str,
        certificate_no: str,
        store_name: str,
        requestid: str = "",
    ) -> RpaVerificationResult:
        """执行验真并返回带 task_id 的结果。"""
        result = self._client.verify(
            certificate_no=certificate_no,
            store_name=store_name,
            requestid=requestid,
        )
        result.task_id = task_id
        result.attempts += 1
        # 记录 jobUuid → task_id 映射供回调使用
        raw = result.raw_response
        if isinstance(raw, dict):
            job_uuid = raw.get("jobUuid") or ""
            if job_uuid:
                _job_task_map[job_uuid] = task_id
        return result

    def handle_callback(
        self,
        payload: YindaoCallbackPayload,
        task_id: str,
        certificate_no: str,
    ) -> RpaVerificationResult:
        """处理影刀回调，返回验真结果。"""
        result = self._client.parse_callback(payload, certificate_no)
        result.task_id = task_id
        return result

    @staticmethod
    def lookup_task_id_by_job_uuid(job_uuid: str) -> str | None:
        """根据影刀 jobUuid 查找关联的审核任务 ID。"""
        return _job_task_map.get(job_uuid)

    @staticmethod
    def to_skill_result_dict(
        result: RpaVerificationResult,
        raw_yindao_response: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """将验真结果转为可存入 skill_result 的 dict。"""
        d: dict[str, Any] = {
            "status": result.status.value,
            "certificate_no": result.certificate_no,
            "verified_at": result.verified_at.isoformat() if result.verified_at else None,
            "screenshot_url": result.screenshot_url,
            "result_label": result.result_label,
            "error_message": result.error_message,
            "attempts": result.attempts,
        }
        if raw_yindao_response:
            d["raw_yindao_response"] = raw_yindao_response
        return d


def _parse_iso_or_now(s: str | None) -> datetime:
    if s:
        try:
            return datetime.fromisoformat(s)
        except (ValueError, TypeError):
            pass
    return datetime.now(tz=timezone.utc)
