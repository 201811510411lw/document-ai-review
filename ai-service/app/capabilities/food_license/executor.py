from app.capabilities.food_license.prompt import FOOD_LICENSE_SYSTEM_PROMPT
from app.capabilities.food_license.schemas import FoodLicenseCapabilityResult
from app.workflows.food_license.state import FoodLicenseWorkflowState


def build_food_license_capability_result(
    workflow_state: FoodLicenseWorkflowState,
) -> FoodLicenseCapabilityResult:
    return FoodLicenseCapabilityResult(
        document_input=workflow_state.get("document_input"),
        document_classification=workflow_state["document_classification"],
        extracted_fields=workflow_state["extracted_fields"],
        normalized_fields=workflow_state["normalized_fields"],
        extraction_metadata={
            **workflow_state.get("extraction_metadata", {}),
            "system_prompt": FOOD_LICENSE_SYSTEM_PROMPT,
        },
    )
