from datetime import datetime, timezone

from app.models import (
    ManualReview,
    ManualReviewStatus,
    ReviewInput,
    ReviewResult,
    ReviewStatus,
    RiskLevel,
)
from app.repositories import SQLiteReviewResultRepository
from app.services.review_service import ReviewService


def build_review_result(task_id: str = "review-task-sqlite") -> ReviewResult:
    now = datetime(2026, 6, 8, 14, 30, tzinfo=timezone.utc)
    return ReviewResult(
        task_id=task_id,
        skill_name="food_license",
        skill_version="v1",
        ruleset_version="food-license-rules-v1",
        document_type="food_license",
        status=ReviewStatus.REVIEWED,
        risk_level=RiskLevel.NONE,
        needs_manual_review=False,
        rule_results=[],
        summary="未发现确定性规则风险。",
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


def test_sqlite_repository_saves_and_gets_review_result_by_task_id(tmp_path):
    repository = SQLiteReviewResultRepository(tmp_path / "reviews.sqlite3")
    result = build_review_result()

    repository.save(result)
    loaded = repository.get_by_task_id(result.task_id)

    assert isinstance(loaded, ReviewResult)
    assert loaded.model_dump(mode="json") == result.model_dump(mode="json")
    assert loaded.skill_result["extracted_fields"]["license_no"] == "JY15101000000000"


def test_sqlite_repository_returns_none_for_missing_task(tmp_path):
    repository = SQLiteReviewResultRepository(tmp_path / "reviews.sqlite3")

    assert repository.get_by_task_id("missing-task") is None


def test_review_service_can_save_result_with_injected_repository(monkeypatch, tmp_path):
    repository = SQLiteReviewResultRepository(tmp_path / "reviews.sqlite3")
    result = build_review_result("review-task-000001")

    class StubSkill:
        name = "food_license"
        version = "v1"
        ruleset_version = "food-license-rules-v1"

        def review(self, input_context):
            return result.model_copy(update={"task_id": input_context.task_id})

    class StubRegistry:
        def get(self, skill_name):
            return StubSkill()

    from app.services import review_service as review_service_module

    monkeypatch.setattr(review_service_module, "skill_registry", StubRegistry())

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
