from itertools import count
from typing import Protocol

from app.models import ReviewInput, ReviewInputContext, ReviewResult
from app.skills.registry import skill_registry


class ReviewResultRepository(Protocol):
    def save(self, review_result: ReviewResult) -> None:
        ...


class ReviewService:
    def __init__(self, repository: ReviewResultRepository | None = None) -> None:
        self._task_sequence = count(1)
        self.repository = repository

    def review_food_license(self, review_input: ReviewInput) -> ReviewResult:
        return self.review(review_input, skill_name="food_license")

    def review(
        self,
        review_input: ReviewInput,
        skill_name: str | None = None,
    ) -> ReviewResult:
        task_id = f"review-task-{next(self._task_sequence):06d}"
        if skill_name is None:
            provisional_context = ReviewInputContext(
                task_id=task_id,
                input=review_input,
                skill_name="",
                skill_version="",
                ruleset_version="",
            )
            skill = skill_registry.select(provisional_context)
        else:
            skill = skill_registry.get(skill_name)

        input_context = ReviewInputContext(
            task_id=task_id,
            input=review_input,
            skill_name=skill.name,
            skill_version=skill.version,
            ruleset_version=skill.ruleset_version,
        )
        result = skill.review(input_context)
        if self.repository is not None:
            self.repository.save(result)
        return result


review_service = ReviewService()
