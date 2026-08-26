import logging
import threading
import time

from app.api.tobacco_license_consistency import _oa_response
from app.repositories.review_result_repository import MySQLReviewResultRepository
from app.services.oa_auto_review_callback import OaAutoReviewCallbackPayload, OaAutoReviewCallbackClient
from app.services.oa_tobacco_auto_review import OaTobaccoAutoReviewService

logger = logging.getLogger(__name__)


class OaReviewRecoveryScheduler:
    """Recovers stale claims and retries callbacks persisted in review_results."""

    def __init__(self, repository: MySQLReviewResultRepository, callback_client: OaAutoReviewCallbackClient, interval_seconds: int = 60):
        self._repository = repository
        self._callback_client = callback_client
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
        recovered = service.recover_stale_claims()
        if recovered:
            logger.warning("[OA恢复] 回收超时任务数量=%s", recovered)
        for result in self._repository.list_review_results():
            if result.document_type != "business_tobacco_consistency" or result.status == "RUNNING":
                continue
            callback = dict((result.skill_result or {}).get("oa_callback") or {})
            if callback.get("status") not in {"PENDING", "FAILED"}:
                continue
            claim = dict((result.skill_result or {}).get("oa_claim") or {})
            if not claim.get("requestid") or not claim.get("workflow_id") or not claim.get("store_code"):
                continue
            payload = OaAutoReviewCallbackPayload(
                workflow_id=int(claim["workflow_id"]),
                requestid=int(claim["requestid"]),
                store_code=str(claim["store_code"]),
                result=_oa_response(result),
            )
            try:
                self._callback_client.send(payload)
            except Exception as error:
                service.update_callback_state(result.task_id, status="FAILED", error=str(error))
                logger.exception("[OA恢复][回调失败] task_id=%s", result.task_id)
            else:
                service.update_callback_state(result.task_id, status="SENT")

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                self.run_once()
            except Exception:
                logger.exception("[OA恢复] 扫描失败")
