from typing import Any

from app.models import ReviewInputContext


def run_contract_workflow(input_context: ReviewInputContext) -> dict[str, Any]:
    return {
        "implementation_status": "not_implemented",
        "skill_name": input_context.skill_name,
        "message": "contract workflow boundary is present but not implemented.",
    }
