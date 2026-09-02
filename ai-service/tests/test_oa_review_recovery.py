from datetime import datetime, timezone

from app.integrations.starrocks.tobacco_license_sources import TobaccoLicenseSourceFile
from app.models import ManualReview, ManualReviewStatus, ReviewResult, ReviewStatus, RiskLevel
from app.services.oa_review_recovery import OaReviewRecoveryScheduler
from app.services.tobacco_license_files import TobaccoLicenseStoredDocument, TobaccoLicenseStoredFile


class RecordingRepository:
    def __init__(self, result: ReviewResult) -> None:
        self.result = result
        self.saved: list[ReviewResult] = []

    def list_review_results(self) -> list[ReviewResult]:
        return [self.saved[-1] if self.saved else self.result]

    def save(self, result: ReviewResult) -> None:
        self.saved.append(result)

    def get_by_task_id(self, task_id: str) -> ReviewResult | None:
        result = self.saved[-1] if self.saved else self.result
        return result if result.task_id == task_id else None


class CapturingCallbackClient:
    def __init__(self) -> None:
        self.payloads = []

    def send(self, payload):
        self.payloads.append(payload)


class RecordingFileStore:
    def __init__(self, stored: list[TobaccoLicenseStoredDocument]) -> None:
        self.stored = stored
        self.calls = 0

    def store_source_files(self, source_files):
        self.calls += 1
        return self.stored


def test_recovery_does_not_backfill_fresh_running_claim(monkeypatch):
    source, stored = _source_and_stored_document()
    source_queries = []
    monkeypatch.setattr(
        "app.services.oa_review_recovery.fetch_tobacco_license_source_files_by_request",
        lambda *args, **kwargs: source_queries.append((args, kwargs)) or [source],
    )
    repository = RecordingRepository(_running_result())
    file_store = RecordingFileStore([stored])
    scheduler = OaReviewRecoveryScheduler(
        repository=repository,
        callback_client=object(),
        source_client=object(),
        file_store=file_store,
    )

    scheduler.run_once()

    assert source_queries == []
    assert file_store.calls == 0
    assert repository.saved == []


def test_recovery_still_backfills_terminal_result(monkeypatch):
    source, stored = _source_and_stored_document()
    source_queries = []
    monkeypatch.setattr(
        "app.services.oa_review_recovery.fetch_tobacco_license_source_files_by_request",
        lambda *args, **kwargs: source_queries.append((args, kwargs)) or [source],
    )
    repository = RecordingRepository(_result(ReviewStatus.FAILED))
    file_store = RecordingFileStore([stored])
    scheduler = OaReviewRecoveryScheduler(
        repository=repository,
        callback_client=object(),
        source_client=object(),
        file_store=file_store,
    )

    scheduler.run_once()

    assert len(source_queries) == 1
    assert file_store.calls == 1
    assert len(repository.saved) == 1
    source_evidence = repository.saved[0].skill_result["source_evidence"]["source"]
    assert source_evidence["requestid"] == 584412
    assert source_evidence["workflow_id"] == 614


def test_recovery_callback_preserves_submission_version():
    result = _result(ReviewStatus.PENDING_MANUAL_REVIEW).model_copy(
        update={
            "task_id": "tc-oa-614-584412-s2",
            "skill_result": {
                "oa_claim": {
                    "workflow_id": 614,
                    "requestid": 584412,
                    "submission_version": 2,
                    "store_code": "00001",
                },
                "oa_callback": {"status": "PENDING"},
            },
        }
    )
    repository = RecordingRepository(result)
    callback_client = CapturingCallbackClient()
    scheduler = OaReviewRecoveryScheduler(
        repository=repository,
        callback_client=callback_client,
    )

    scheduler.run_once()

    assert callback_client.payloads[0].submission_version == 2
    assert callback_client.payloads[0].result["data"]["task_id"] == result.task_id


def _source_and_stored_document():
    source = TobaccoLicenseSourceFile(
        requestid=584412,
        workflow_id=614,
        store_code="00001",
        document_role="business_license",
        file_real_path="/data/license.zip",
        docid=1001,
        imagefile_id=2001,
    )
    stored = TobaccoLicenseStoredDocument(
        source=source,
        output_dir="/document-ai-review/tobacco_license/00001/584412_1001_2001",
        files=[
            TobaccoLicenseStoredFile(
                file_name="business-license.jpg",
                relative_path="00001/584412_1001_2001/business-license.jpg",
                local_path="/document-ai-review/tobacco_license/00001/584412_1001_2001/business-license.jpg",
                content_type="image/jpeg",
                file_size=1024,
            )
        ],
    )
    return source, stored


def _running_result() -> ReviewResult:
    return _result(ReviewStatus.RUNNING)


def _result(status: ReviewStatus) -> ReviewResult:
    now = datetime.now(timezone.utc)
    skill_result = {
        "oa_claim": {
            "workflow_id": 614,
            "requestid": 584412,
            "store_code": "00001",
        }
    }
    if status != ReviewStatus.RUNNING:
        skill_result["oa_callback"] = {"status": "SENT"}
    return ReviewResult(
        task_id="tc-oa-614-584412",
        use_case_name="tobacco_license_consistency_review",
        use_case_version="v1",
        skill_name="tobacco_license_consistency_review",
        skill_version="v1",
        ruleset_version="v1",
        document_type="business_tobacco_consistency",
        status=status,
        risk_level=RiskLevel.NONE,
        needs_manual_review=False,
        rule_results=[],
        summary="OA 自动审核执行中",
        manual_review=ManualReview(status=ManualReviewStatus.NOT_REQUIRED),
        created_at=now,
        updated_at=now,
        skill_result=skill_result,
    )
