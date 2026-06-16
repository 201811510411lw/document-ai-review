from typing import Any

from app.models import ReviewInputContext


def run_contract_workflow(input_context: ReviewInputContext) -> dict[str, Any]:
    return {
        "implementation_status": "not_implemented",
        "use_case_name": input_context.use_case_name,
        "message": "contract workflow boundary is present but not implemented.",
    }
