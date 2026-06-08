from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.models import (
    ManualReviewAction,
    ManualReviewStatus,
    ReviewInput,
    ReviewInputContext,
    ReviewResult,
    ReviewStatus,
)
from app.repositories.sqlite_review_repository import SQLiteReviewRepository
from app.skills.registry import skill_registry


class ReviewService:
    def __init__(self, repository: SQLiteReviewRepository | None = None) -> None:
        self._repository = repository or SQLiteReviewRepository()

    def review_food_license(self, review_input: ReviewInput) -> ReviewResult:
        skill = skill_registry.get("food_license")
        task_id = f"review-task-{uuid4().hex}"
        input_context = ReviewInputContext(
            task_id=task_id,
            input=review_input,
            skill_name=skill.name,
            skill_version=skill.version,
            ruleset_version=skill.ruleset_version,
        )
        review_result = skill.review(input_context)
        return self._repository.save(review_result)

    def get_review(self, task_id: str) -> ReviewResult | None:
        return self._repository.get(task_id)

    def submit_manual_review(
        self,
        task_id: str,
        manual_review_action: ManualReviewAction,
    ) -> ReviewResult | None:
        review_result = self._repository.get(task_id)
        if review_result is None:
            return None

        updated_manual_review = review_result.manual_review.model_copy(
            update={
                "status": ManualReviewStatus.COMPLETED,
                "reviewer": manual_review_action.reviewer,
                "action": manual_review_action.action,
                "comment": manual_review_action.comment,
                "reviewed_at": datetime.now(ZoneInfo(settings.timezone)),
            }
        )
        updated_result = review_result.model_copy(
            update={
                "status": ReviewStatus.MANUAL_REVIEWED,
                "needs_manual_review": False,
                "manual_review": updated_manual_review,
                "updated_at": datetime.now(ZoneInfo(settings.timezone)),
            }
        )
        return self._repository.save(updated_result)


review_service = ReviewService()
