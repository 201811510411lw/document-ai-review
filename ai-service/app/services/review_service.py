from typing import Any, Protocol
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
        task_id = _task_id_for_input(review_input)
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
        reroute_document_type = _reroute_document_type(
            review_input=review_input,
            result=result,
        )
        if reroute_document_type:
            rerouted_entry = _get_runtime_entry(
                _use_case_for_document_type(reroute_document_type)
            )
            rerouted_graph = rerouted_entry.definition
            rerouted_input = review_input.model_copy(
                update={
                    "declared_document_type": reroute_document_type,
                    "source": {
                        **review_input.source,
                        "original_declared_document_type": review_input.declared_document_type,
                        "content_rerouted_document_type": reroute_document_type,
                        "content_reroute_reason": "recognized_document_type_conflicts_with_source_declaration",
                    },
                }
            )
            result = rerouted_entry.invoke(
                ReviewInputContext(
                    task_id=task_id,
                    input=rerouted_input,
                    use_case_name=rerouted_graph["name"],
                    use_case_version=rerouted_graph["version"],
                    ruleset_version=rerouted_graph["ruleset_version"],
                )
            )
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


def _task_id_for_input(review_input: ReviewInput) -> str:
    source_record_id = str(review_input.source.get("record_id") or "").strip()
    if source_record_id:
        return f"review-task-{source_record_id}"
    return f"review-task-{uuid4()}"


_DOCUMENT_TYPE_TO_USE_CASE = {
    "business_license": "business_license",
    "food_license": "food_license",
    "food_production_license": "food_production_license",
    "tobacco_license": "tobacco_license",
    "product_report": "qc_document_review",
    "batch_report": "qc_document_review",
}


def _reroute_document_type(*, review_input: ReviewInput, result: ReviewResult) -> str | None:
    """内容类型明确且与来源声明不同时，只重路由一次到对应工作流。"""
    recognized_type = _recognized_document_type(result)
    declared_type = _normalize_document_type(review_input.declared_document_type)
    if not recognized_type or recognized_type == declared_type:
        return None
    if recognized_type not in _DOCUMENT_TYPE_TO_USE_CASE:
        return None
    return recognized_type


def _recognized_document_type(result: ReviewResult) -> str | None:
    skill_result = result.skill_result if isinstance(result.skill_result, dict) else {}
    extracted_fields = skill_result.get("extracted_fields") or {}
    candidates: list[Any] = [
        # 证照页面可见标题优先于初始入口写入的默认 document_type。
        extracted_fields.get("document_type_raw"),
        (skill_result.get("document_classification") or {}).get("document_type"),
        extracted_fields.get("document_type"),
        (skill_result.get("document") or {}).get("document_type"),
        result.document_type,
    ]
    for candidate in candidates:
        normalized = _normalize_document_type(candidate)
        if normalized in _DOCUMENT_TYPE_TO_USE_CASE:
            return normalized
    return None


def _normalize_document_type(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    aliases = {
        "营业执照": "business_license",
        "食品经营许可证": "food_license",
        "食品生产许可证": "food_production_license",
        "烟草专卖零售许可证": "tobacco_license",
        "商品报告": "product_report",
        "产品报告": "product_report",
        "商品批次报告": "batch_report",
        "批次报告": "batch_report",
    }
    normalized = aliases.get(text, text.lower())
    if normalized in _DOCUMENT_TYPE_TO_USE_CASE:
        return normalized

    from app.capabilities.document_type_mapping import display_to_system, match_document_type

    display_name = match_document_type(text)
    return display_to_system(display_name) if display_name else None


def _use_case_for_document_type(document_type: str) -> str:
    return _DOCUMENT_TYPE_TO_USE_CASE[document_type]
