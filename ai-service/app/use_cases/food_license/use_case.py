from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.models import (
    AuditEvent,
    ReviewInputContext,
    ReviewResult,
    ReviewStatus,
)
from app.capabilities.food_license.executor import build_food_license_capability_result
from app.workflows.food_license import run_food_license_workflow


class FoodLicenseUseCase:
    name = "food_license"
    version = "v1"
    ruleset_version = "food-license-rules-v1"
    supported_document_types = ("food_license",)

    def supports(self, input_context: ReviewInputContext) -> bool:
        declared_document_type = input_context.input.declared_document_type
        return declared_document_type in (None, "food_license")

    def review(self, input_context: ReviewInputContext) -> ReviewResult:
        now = datetime.now(ZoneInfo(settings.timezone))
        workflow_state = run_food_license_workflow(input_context)
        capability_result = build_food_license_capability_result(workflow_state)

        return ReviewResult(
            task_id=input_context.task_id,
            use_case_name=self.name,
            use_case_version=self.version,
            skill_name=self.name,
            skill_version=self.version,
            ruleset_version=self.ruleset_version,
            capability_names=["food_license"],
            document_type="food_license",
            status=ReviewStatus.REVIEWED,
            risk_level=workflow_state["risk_level"],
            needs_manual_review=workflow_state["needs_manual_review"],
            rule_results=workflow_state["rule_results"],
            summary=workflow_state["summary"],
            manual_review=workflow_state["manual_review"],
            audit_events=[
                AuditEvent(
                    event_type="food_license.workflow.completed",
                    message="food_license 内部工作流执行完成",
                    occurred_at=now,
                )
            ],
            created_at=now,
            updated_at=now,
            skill_result=capability_result,
        )


food_license_use_case = FoodLicenseUseCase()
