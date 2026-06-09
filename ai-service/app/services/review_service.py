from itertools import count

from app.models import ReviewInput, ReviewInputContext, ReviewResult
from app.skills.registry import skill_registry


class ReviewService:
    def __init__(self) -> None:
        self._task_sequence = count(1)

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
        return skill.review(input_context)


review_service = ReviewService()
