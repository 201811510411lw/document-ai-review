import logging
import threading
import time

from app.api.tobacco_license_consistency import _oa_callback_response, _oa_callback_state
from app.integrations.mysql_client import MySqlFetchClient
from app.integrations.starrocks.tobacco_license_sources import (
    OA_MYSQL_TOBACCO_SOURCE_TABLES,
    fetch_tobacco_license_source_files_by_request,
)
from app.models import ReviewStatus
from app.repositories.review_result_repository import MySQLReviewResultRepository
from app.services.oa_auto_review_callback import OaAutoReviewCallbackPayload, OaAutoReviewCallbackClient
from app.services.oa_tobacco_auto_review import OaTobaccoAutoReviewService, _oa_source_snapshot
from app.services.tobacco_license_files import TobaccoLicenseFileStore

logger = logging.getLogger(__name__)


class OaReviewRecoveryScheduler:
    """Recovers stale claims and retries callbacks persisted in review_results."""

    def __init__(self, repository: MySQLReviewResultRepository, callback_client: OaAutoReviewCallbackClient, source_client: MySqlFetchClient | None = None, file_store: TobaccoLicenseFileStore | None = None, interval_seconds: int = 60):
        self._repository = repository
        self._callback_client = callback_client
        self._source_client = source_client
        self._file_store = file_store
        self._interval_seconds = max(10, interval_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="oa-review-recovery", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def run_once(self) -> None:
        service = OaTobaccoAutoReviewService(
            sql_client=None, file_store=None, repository=self._repository, document_review_service=None
        )
        self._backfill_source_evidence(service)
        recovered = service.recover_stale_claims()
        if recovered:
            logger.warning("[OA恢复] 回收超时任务数量=%s", recovered)
        for result in self._repository.list_review_results():
            if (
                result.document_type != "business_tobacco_consistency"
                or result.status == ReviewStatus.RUNNING
            ):
                continue
            callback = dict((result.skill_result or {}).get("oa_callback") or {})
            if callback.get("status") not in {None, "PENDING", "FAILED"}:
                continue
            claim = dict((result.skill_result or {}).get("oa_claim") or {})
            if not claim.get("requestid") or not claim.get("workflow_id") or not claim.get("store_code"):
                logger.warning(
                    "[OA恢复][回调跳过] task_id=%s 缺少完整 OA claim",
                    result.task_id,
                )
                continue
            payload = OaAutoReviewCallbackPayload(
                workflow_id=int(claim["workflow_id"]),
                requestid=int(claim["requestid"]),
                submission_version=int(claim.get("submission_version") or 1),
                store_code=str(claim["store_code"]),
                result=_oa_callback_response(result),
            )
            service.update_callback_state(result.task_id, status="PENDING")
            try:
                delivery = self._callback_client.send(payload)
            except Exception as error:
                service.update_callback_state(
                    result.task_id,
                    status="FAILED",
                    error=str(error),
                    callback_state=_oa_callback_state(
                        "FAILED",
                        error=str(error),
                        trigger="recovery",
                        request_payload=payload,
                        delivery=getattr(error, "delivery", None),
                    ),
                )
                logger.exception("[OA恢复][回调失败] task_id=%s", result.task_id)
            else:
                service.update_callback_state(
                    result.task_id,
                    status="SENT",
                    callback_state=_oa_callback_state(
                        "SENT",
                        trigger="recovery",
                        request_payload=payload,
                        delivery=delivery,
                    ),
                )

    def _backfill_source_evidence(self, service: OaTobaccoAutoReviewService) -> None:
        if self._source_client is None or self._file_store is None:
            return
        for result in self._repository.list_review_results():
            if (
                result.document_type != "business_tobacco_consistency"
                or result.status == ReviewStatus.RUNNING
            ):
                continue
            skill_result = dict(result.skill_result or {})
            claim = dict(skill_result.get("oa_claim") or {})
            source = dict((skill_result.get("source_evidence") or {}).get("source") or {})
            oa_snapshot = dict(source.get("oa") or {})
            attachments = list(oa_snapshot.get("attachments") or [])
            if claim.get("store_code") and any(item.get("relative_path") for item in attachments):
                continue
            if not claim.get("requestid") or not claim.get("workflow_id"):
                continue
            try:
                source_files = fetch_tobacco_license_source_files_by_request(
                    self._source_client,
                    int(claim["requestid"]),
                    workflow_id=int(claim["workflow_id"]),
                )
                stored = self._file_store.store_source_files(source_files)
                if not source_files or not stored:
                    continue
                source = _oa_source_snapshot(
                    source_files[0],
                    source_files=source_files,
                    stored_documents=stored,
                    selected_files=[],
                )
                store_code = str(source_files[0].store_code or "").strip()
                if not store_code:
                    logger.warning(
                        "[OA恢复][来源补偿跳过] task_id=%s requestid=%s 缺少 store_code",
                        result.task_id,
                        claim["requestid"],
                    )
                    continue
                claim["store_code"] = store_code
                skill_result["oa_claim"] = claim
                skill_result["source_evidence"] = {
                    "source": {
                        "requestid": source_files[0].requestid,
                        "workflow_id": source_files[0].workflow_id,
                        "oa": source,
                    }
                }
                self._repository.save(result.model_copy(update={"skill_result": skill_result}))
            except Exception:
                logger.exception("[OA恢复][来源补偿失败] task_id=%s", result.task_id)

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                self.run_once()
            except Exception:
                logger.exception("[OA恢复] 扫描失败")
