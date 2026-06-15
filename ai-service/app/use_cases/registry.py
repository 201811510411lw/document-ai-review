from app.models import ReviewInputContext
from app.use_cases.base import UseCase
from app.use_cases.business_license import business_license_use_case
from app.use_cases.contract_review import contract_review_use_case
from app.use_cases.food_license import food_license_use_case
from app.use_cases.qc_document_review import qc_document_review_use_case
from app.use_cases.tobacco_license import tobacco_license_use_case
from app.use_cases.tobacco_license_consistency_review import (
    tobacco_license_consistency_review_use_case,
)


class UseCaseRegistry:
    def __init__(self) -> None:
        self._use_cases: dict[str, UseCase] = {}

    def register(self, use_case: UseCase) -> None:
        self._use_cases[use_case.name] = use_case

    def get(self, use_case_name: str) -> UseCase:
        return self._use_cases[use_case_name]

    def list(self) -> list[UseCase]:
        return list(self._use_cases.values())

    def select(self, input_context: ReviewInputContext) -> UseCase:
        candidates = [
            use_case
            for use_case in self._use_cases.values()
            if use_case.supports(input_context)
        ]
        if not candidates:
            raise LookupError("No registered use case supports the input context.")
        if len(candidates) == 1:
            return candidates[0]

        declared_document_type = input_context.input.declared_document_type
        exact_name_matches = [
            use_case
            for use_case in candidates
            if use_case.name == declared_document_type
        ]
        if len(exact_name_matches) == 1:
            return exact_name_matches[0]

        candidate_names = ", ".join(use_case.name for use_case in candidates)
        raise ValueError(
            "Multiple registered use cases support the input context: "
            f"{candidate_names}"
        )


use_case_registry = UseCaseRegistry()
use_case_registry.register(business_license_use_case)
use_case_registry.register(food_license_use_case)
use_case_registry.register(qc_document_review_use_case)
use_case_registry.register(tobacco_license_use_case)
use_case_registry.register(tobacco_license_consistency_review_use_case)
use_case_registry.register(contract_review_use_case)
