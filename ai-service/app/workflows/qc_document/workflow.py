from typing import Any

from app.models import ReviewInputContext


def run_qc_document_workflow(input_context: ReviewInputContext) -> dict[str, Any]:
    return {
        "implementation_status": "not_implemented",
        "skill_name": input_context.skill_name,
        "message": "qc_document workflow boundary is present but not implemented.",
    }
