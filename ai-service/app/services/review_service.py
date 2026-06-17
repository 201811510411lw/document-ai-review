from typing import Protocol
from uuid import uuid4

from app.models import ReviewInput, ReviewInputContext, ReviewResult
from app.repositories import build_review_result_repository_from_env
from app.services.wecom_notifications import enqueue_review_notification
from app.workflows.registry import review_graph_registry


class ReviewResultRepository(Protocol):
    def save(self, review_result: ReviewResult) -> None:
        ...


class ReviewService:
    def __init__(self, repository: ReviewResultRepository | None = None) -> None:
        self.repository = repository

    def review_food_license(self, review_input: ReviewInput) -> ReviewResult:
        return self.review(review_input, use_case_name="food_license")

    def review(
        self,
        review_input: ReviewInput,
        use_case_name: str | None = None,
    ) -> ReviewResult:
        task_id = f"review-task-{uuid4()}"
        if use_case_name is None:
            provisional_context = ReviewInputContext(
                task_id=task_id,
                input=review_input,
                use_case_name="",
                use_case_version="",
                ruleset_version="",
            )
            runtime_entry = _select_runtime_entry(provisional_context)
        else:
            runtime_entry = _get_runtime_entry(use_case_name)

        graph = runtime_entry.definition
        input_context = ReviewInputContext(
            task_id=task_id,
            input=review_input,
            use_case_name=graph["name"],
            use_case_version=graph["version"],
            ruleset_version=graph["ruleset_version"],
        )
        result = runtime_entry.invoke(input_context)
        self._save_result(result)
        return result

    def _save_result(self, result: ReviewResult) -> None:
        if self.repository is not None:
            self.repository.save(result)
            if hasattr(self.repository, "enqueue_wecom_notification"):
                enqueue_review_notification(self.repository, result)


review_service = ReviewService(repository=build_review_result_repository_from_env())


def _get_runtime_entry(use_case_name: str):
    return review_graph_registry.get_entry(use_case_name)


def _select_runtime_entry(input_context: ReviewInputContext):
    return review_graph_registry.select_entry(input_context)
