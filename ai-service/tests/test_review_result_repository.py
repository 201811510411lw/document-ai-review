from datetime import datetime, timezone

from app.models import (
    ManualReview,
    ManualReviewStatus,
    ReviewInput,
    ReviewResult,
    ReviewStatus,
    RiskLevel,
)
from app.integrations.mysql_client import MySqlSettings
from app.repositories import MySQLReviewResultRepository
from app.services.review_service import ReviewService
from tests.mysql_repository_stub import install_mysql_repository_stub


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


def test_review_service_can_save_result_with_injected_mysql_repository(monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    repository = _repository()
    result = build_review_result("review-task-000001")

    class StubUseCase:
        name = "food_license"
        version = "v1"
        ruleset_version = "food-license-rules-v1"

        def review(self, input_context):
            return result.model_copy(update={"task_id": input_context.task_id})

    class StubRegistry:
        def get(self, use_case_name):
            return StubUseCase()

    from app.services import review_service as review_service_module

    monkeypatch.setattr(review_service_module, "use_case_registry", StubRegistry())

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
