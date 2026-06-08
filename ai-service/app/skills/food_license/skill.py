from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.models import (
    AuditEvent,
    ManualReview,
    ManualReviewStatus,
    ReviewInputContext,
    ReviewResult,
    ReviewStatus,
)
from app.skills.food_license.graph import food_license_graph
from app.skills.food_license.models import (
    FoodLicenseSkillResult,
)


class FoodLicenseSkill:
    name = "food_license"
    version = "v1"
    ruleset_version = "food-license-rules-v1"
    supported_document_types = ("food_license",)

    def supports(self, input_context: ReviewInputContext) -> bool:
        declared_document_type = input_context.input.declared_document_type
        return declared_document_type in (None, "food_license")

    def review(self, input_context: ReviewInputContext) -> ReviewResult:
        now = datetime.now(ZoneInfo(settings.timezone))
        workflow_state = food_license_graph.invoke({"input_context": input_context})
        skill_result = FoodLicenseSkillResult(
            document_classification=workflow_state["document_classification"],
            extracted_fields=workflow_state["extracted_fields"],
            normalized_fields=workflow_state["normalized_fields"],
        )

        return ReviewResult(
            task_id=input_context.task_id,
            skill_name=self.name,
            skill_version=self.version,
            ruleset_version=self.ruleset_version,
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
            skill_result=skill_result,
        )


food_license_skill = FoodLicenseSkill()
