from datetime import datetime
from zoneinfo import ZoneInfo

from app.capabilities.tobacco_license.executor import build_tobacco_license_capability_result
from app.core.config import settings
from app.models import AuditEvent, ReviewInputContext, ReviewResult, ReviewStatus, RiskLevel
from app.workflows.tobacco_license import run_tobacco_license_workflow


class TobaccoLicenseUseCase:
    name = "tobacco_license"
    version = "v1"
    ruleset_version = "tobacco-license-rules-v1"
    supported_document_types = ("tobacco_license",)

    def supports(self, input_context: ReviewInputContext) -> bool:
        return input_context.input.declared_document_type in self.supported_document_types

    def review(self, input_context: ReviewInputContext) -> ReviewResult:
        now = datetime.now(ZoneInfo(settings.timezone))
        workflow_state = run_tobacco_license_workflow(input_context)
        capability_result = build_tobacco_license_capability_result(workflow_state)
        return ReviewResult.model_validate(
            {
                "task_id": input_context.task_id,
                "use_case_name": self.name,
                "use_case_version": self.version,
                "skill_name": self.name,
                "skill_version": self.version,
                "ruleset_version": self.ruleset_version,
                "capability_names": ["tobacco_license"],
                "document_type": "tobacco_license",
                "status": (
                    ReviewStatus.PENDING_MANUAL_REVIEW
                    if workflow_state.get("needs_manual_review", True)
                    else ReviewStatus.REVIEWED
                ),
                "risk_level": workflow_state.get("risk_level", RiskLevel.MEDIUM),
                "needs_manual_review": workflow_state.get("needs_manual_review", True),
                "rule_results": workflow_state.get("rule_results", []),
                "summary": workflow_state.get("summary", "烟草证审核结果不完整。"),
                "manual_review": workflow_state.get("manual_review"),
                "audit_events": [
                    AuditEvent(
                        event_type="tobacco_license.workflow.completed",
                        message="tobacco_license 内部工作流执行完成",
                        occurred_at=now,
                    )
                ],
                "created_at": now,
                "updated_at": now,
                "skill_result": capability_result.model_dump(mode="json"),
            }
        )


tobacco_license_use_case = TobaccoLicenseUseCase()
