from itertools import count
from typing import Protocol

from app.models import ReviewInput, ReviewInputContext, ReviewResult
from app.use_cases.registry import use_case_registry


class ReviewResultRepository(Protocol):
    def save(self, review_result: ReviewResult) -> None:
        ...


class ReviewService:
    def __init__(self, repository: ReviewResultRepository | None = None) -> None:
        self._task_sequence = count(1)
        self.repository = repository

    def review_food_license(self, review_input: ReviewInput) -> ReviewResult:
        return self.review(review_input, use_case_name="food_license")

    def review(
        self,
        review_input: ReviewInput,
        use_case_name: str | None = None,
    ) -> ReviewResult:
        task_id = f"review-task-{next(self._task_sequence):06d}"
        if use_case_name is None:
            provisional_context = ReviewInputContext(
                task_id=task_id,
                input=review_input,
                use_case_name="",
                use_case_version="",
                ruleset_version="",
            )
            use_case = use_case_registry.select(provisional_context)
        else:
            use_case = use_case_registry.get(use_case_name)

        input_context = ReviewInputContext(
            task_id=task_id,
            input=review_input,
            use_case_name=use_case.name,
            use_case_version=use_case.version,
            ruleset_version=use_case.ruleset_version,
        )
        result = use_case.review(input_context)
        if self.repository is not None:
            self.repository.save(result)
        return result


review_service = ReviewService()
