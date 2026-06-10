from datetime import datetime
from zoneinfo import ZoneInfo

from app.capabilities.business_license.executor import (
    build_business_license_capability_result,
)
from app.core.config import settings
from app.models import AuditEvent, ReviewInputContext, ReviewResult, RiskLevel
from app.workflows.business_license import run_business_license_workflow


class BusinessLicenseUseCase:
    name = "business_license"
    version = "v1"
    ruleset_version = "business-license-rules-v1"
    supported_document_types = ("business_license",)

    def supports(self, input_context: ReviewInputContext) -> bool:
        return input_context.input.declared_document_type in self.supported_document_types

    def review(self, input_context: ReviewInputContext) -> ReviewResult:
        now = datetime.now(ZoneInfo(settings.timezone))
        workflow_state = run_business_license_workflow(input_context)
        capability_result = build_business_license_capability_result(workflow_state)
        return ReviewResult.model_validate(
            {
                "task_id": input_context.task_id,
                "use_case_name": self.name,
                "use_case_version": self.version,
                "skill_name": self.name,
                "skill_version": self.version,
                "ruleset_version": self.ruleset_version,
                "capability_names": ["business_license"],
                "document_type": "business_license",
                "status": workflow_state.get("status"),
                "risk_level": workflow_state.get("risk_level", RiskLevel.MEDIUM),
                "needs_manual_review": workflow_state.get("needs_manual_review", True),
                "rule_results": workflow_state.get("rule_results", []),
                "summary": workflow_state.get("summary", "营业执照审核结果不完整。"),
                "manual_review": workflow_state.get("manual_review"),
                "audit_events": [
                    AuditEvent(
                        event_type="business_license.workflow.completed",
                        message="business_license 内部工作流执行完成",
                        occurred_at=now,
                    )
                ],
                "created_at": now,
                "updated_at": now,
                "skill_result": capability_result.model_dump(mode="json"),
            }
        )


business_license_use_case = BusinessLicenseUseCase()
