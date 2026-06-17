from app.models import ReviewInputContext, ReviewResult
from app.use_cases.business_license import business_license_use_case
from app.use_cases.contract_review import contract_review_use_case
from app.use_cases.food_license import food_license_use_case
from app.use_cases.qc_document_review import qc_document_review_use_case
from app.use_cases.tobacco_license import tobacco_license_use_case
from app.use_cases.tobacco_license_consistency_review import (
    tobacco_license_consistency_review_use_case,
)
from app.workflows.runtime import ReviewGraphDefinition, ReviewGraphRegistry, ReviewRuntimeEntry


def _definition_from_use_case(use_case) -> ReviewGraphDefinition:
    return ReviewGraphDefinition(
        name=use_case.name,
        version=use_case.version,
        ruleset_version=use_case.ruleset_version,
        supported_document_types=use_case.supported_document_types,
        capability_names=(use_case.name,),
    )


def _entry_from_use_case(use_case) -> ReviewRuntimeEntry:
    def invoke(input_context: ReviewInputContext) -> ReviewResult:
        return use_case.review(input_context)

    return ReviewRuntimeEntry(
        definition=_definition_from_use_case(use_case),
        invoke=invoke,
    )


review_graph_registry = ReviewGraphRegistry()
review_graph_registry.register_entry(_entry_from_use_case(business_license_use_case))
review_graph_registry.register_entry(_entry_from_use_case(contract_review_use_case))
review_graph_registry.register_entry(_entry_from_use_case(food_license_use_case))
review_graph_registry.register_entry(_entry_from_use_case(qc_document_review_use_case))
review_graph_registry.register_entry(_entry_from_use_case(tobacco_license_use_case))
review_graph_registry.register_entry(
    _entry_from_use_case(tobacco_license_consistency_review_use_case)
)
