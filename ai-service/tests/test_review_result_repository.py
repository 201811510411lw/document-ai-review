from datetime import datetime, timezone

import pymysql

from app.models import (
    ManualReview,
    ManualReviewStatus,
    ReviewInput,
    ReviewResult,
    ReviewStatus,
    RiskLevel,
)
from app.integrations.mysql_client import MySqlSettings
from app.repositories import (
    MySQLReviewResultRepository,
    build_review_result_repository_from_env,
    reset_review_result_repository_cache,
)
from app.repositories.review_result_repository import _manual_review_payload, _try_create_index
from app.services.review_service import ReviewService
from app.workflows.runtime import ReviewGraphDefinition, ReviewRuntimeEntry
from tests.mysql_repository_stub import install_mysql_repository_stub


class IndexPermissionDeniedCursor:
    def execute(self, _ddl):
        raise pymysql.err.OperationalError(
            1142,
            "INDEX command denied to user for table 'review_summary_index'",
        )


def test_optional_index_creation_does_not_block_read_write_database_user():
    _try_create_index(
        IndexPermissionDeniedCursor(),
        "CREATE INDEX idx_review_summary_frontend_type_created "
        "ON review_summary_index (frontend_status, document_type, created_at)",
    )


def build_review_result(task_id: str = "review-task-mysql") -> ReviewResult:
    now = datetime(2026, 6, 8, 14, 30, tzinfo=timezone.utc)
    return ReviewResult(
        task_id=task_id,
        use_case_name="food_license",
        use_case_version="v1",
        skill_name="food_license",
        skill_version="v1",
        ruleset_version="food-license-rules-v1",
        document_type="food_license",
        status=ReviewStatus.REVIEWED,
        risk_level=RiskLevel.NONE,
        needs_manual_review=False,
        rule_results=[],
        summary="Skill 规则审核通过。",
        manual_review=ManualReview(status=ManualReviewStatus.NOT_REQUIRED),
        audit_events=[],
        created_at=now,
        updated_at=now,
        skill_result={
            "extracted_fields": {
                "license_no": "JY15101000000000",
            }
        },
    )


def build_tobacco_consistency_result(task_id: str) -> ReviewResult:
    result = build_review_result(task_id)
    return result.model_copy(
        update={
            "use_case_name": "tobacco_license_consistency_review",
            "skill_name": "tobacco-license-review",
            "ruleset_version": "tobacco-consistency-rules-v1",
            "document_type": "business_tobacco_consistency",
            "skill_result": {
                "business_license_fields": {"subject_name": "成都示例烟草商行"},
                "tobacco_license_fields": {"license_no": "510101000000"},
                "comparison": {"differences": []},
                "source_evidence": {"source": {"requestid": "OA-001"}},
            },
        }
    )


def test_mysql_repository_saves_and_gets_review_result_by_task_id(monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = build_review_result()

    repository.save(result)
    loaded = repository.get_by_task_id(result.task_id)

    assert isinstance(loaded, ReviewResult)
    assert loaded.model_dump(mode="json") == result.model_dump(mode="json")
    assert loaded.skill_result["extracted_fields"]["license_no"] == "JY15101000000000"


def test_mysql_repository_returns_none_for_missing_task(monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()

    assert repository.get_by_task_id("missing-task") is None


def test_mysql_repository_reads_frontend_review_page_from_summary_projection(monkeypatch):
    storage = install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    repository.save(build_review_result("frontend-page-1"))
    repository.save(build_review_result("frontend-page-2"))

    payload = repository.list_frontend_reviews(
        document_type="food_license",
        review_status="confirmed",
        keyword="规则审核",
        limit=1,
        offset=1,
    )

    assert payload["stats"] == {"total": 2, "pending": 0, "confirmed": 2, "flagged": 0}
    assert payload["filtered_total"] == 2
    assert len(payload["items"]) == 1
    assert payload["items"][0]["frontend_status"] == "confirmed"
    assert sum("SELECT * FROM review_summary_index" in sql for sql in storage["executed_sql"]) == 1

    label_payload = repository.list_frontend_reviews(
        document_type="food_license",
        review_status="confirmed",
        keyword="食品经营许可证",
        limit=20,
        offset=0,
    )

    assert label_payload["filtered_total"] == 2


def test_mysql_repository_claim_is_atomic_and_releasable(monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    claim = build_review_result("tc-oa-614-584412").model_copy(
        update={"status": ReviewStatus.RUNNING}
    )

    assert repository.claim(claim) is True
    assert repository.claim(claim) is False

    repository.release_claim(claim)

    assert repository.claim(claim) is True


def test_mysql_repository_old_claim_cannot_overwrite_new_owner(monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    first_claim = build_review_result("tc-oa-614-584412").model_copy(
        update={"status": ReviewStatus.RUNNING, "skill_result": {"claim": "first"}}
    )
    second_claim = first_claim.model_copy(update={"skill_result": {"claim": "second"}})
    final_result = build_review_result("tc-oa-614-584412")

    assert repository.claim(first_claim) is True
    repository.release_claim(first_claim)
    assert repository.claim(second_claim) is True

    assert repository.complete_claim(first_claim, final_result) is False
    assert repository.get_by_task_id(final_result.task_id).skill_result == {
        "claim": "second"
    }
    assert repository.complete_claim(second_claim, final_result) is True
    assert repository.get_by_task_id(final_result.task_id).status == ReviewStatus.REVIEWED


def test_mysql_repository_save_persists_tobacco_consistency_detail_projection(monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = build_tobacco_consistency_result("tobacco-consistency-save")

    repository.save(result)

    assert repository.get_by_task_id(result.task_id) is not None
    detail = repository.get_tobacco_consistency_snapshot(result.task_id)
    assert detail is not None
    assert detail["document_type"] == "business_tobacco_consistency"


def test_mysql_repository_complete_claim_persists_tobacco_consistency_detail_projection(monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = build_tobacco_consistency_result("tobacco-consistency-claim")
    claim = result.model_copy(update={"status": ReviewStatus.RUNNING})

    assert repository.claim(claim) is True
    assert repository.complete_claim(claim, result) is True

    assert repository.get_by_task_id(result.task_id) is not None
    detail = repository.get_tobacco_consistency_snapshot(result.task_id)
    assert detail is not None
    assert detail["document_type"] == "business_tobacco_consistency"


def test_review_service_can_save_result_with_injected_mysql_repository(monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = build_review_result("review-task-000001")

    class StubRegistry:
        def get_entry(self, graph_name):
            def invoke(input_context):
                return result.model_copy(update={"task_id": input_context.task_id})

            return ReviewRuntimeEntry(
                definition=ReviewGraphDefinition(
                    name="food_license",
                    version="v1",
                    ruleset_version="food-license-rules-v1",
                    supported_document_types=("food_license",),
                    capability_names=("food_license",),
                ),
                invoke=invoke,
            )

    from app.services import review_service as review_service_module

    monkeypatch.setattr(review_service_module, "review_graph_registry", StubRegistry())

    saved = ReviewService(repository=repository).review_food_license(
        ReviewInput(
            ocr_text="食品经营许可证",
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
        )
    )

    loaded = repository.get_by_task_id(saved.task_id)
    assert loaded is not None
    assert loaded.model_dump(mode="json") == saved.model_dump(mode="json")


def test_review_service_without_repository_keeps_existing_no_persistence_behavior():
    service = ReviewService()

    assert service.repository is None


def test_request_more_info_keeps_review_pending():
    reviewed_at = datetime(2026, 8, 4, 10, 0, tzinfo=timezone.utc)

    updated = _manual_review_payload(
        payload_json=build_review_result().model_dump_json(),
        decision="request_more_info",
        comment="请补充清晰证照",
        reviewer_id="reviewer-1",
        reviewer_username="reviewer",
        reviewed_at=reviewed_at,
    )

    assert updated.status == ReviewStatus.PENDING_MANUAL_REVIEW
    assert updated.needs_manual_review is True
    assert updated.manual_review.action == "request_more_info"


def test_mysql_repository_reuses_connection_between_queries(monkeypatch):
    storage = install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = build_review_result("review-task-reuse")

    repository.save(result)
    repository.get_by_task_id(result.task_id)
    repository.get_by_task_id(result.task_id)

    assert len(storage["connections"]) == 1


def test_review_result_repository_builder_reuses_cached_repository(monkeypatch):
    install_mysql_repository_stub(monkeypatch)

    first = build_review_result_repository_from_env()
    second = build_review_result_repository_from_env()

    assert first is second

    reset_review_result_repository_cache()
    third = build_review_result_repository_from_env()

    assert third is not first


def _repository() -> MySQLReviewResultRepository:
    return MySQLReviewResultRepository(
        MySqlSettings(
            host="127.0.0.1",
            port=3306,
            user="review",
            password="secret",
            database="document_ai_review",
        )
    )
