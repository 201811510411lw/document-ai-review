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
    RiskLevel,
)
from app.workflows.tobacco_license import run_tobacco_license_workflow


class TobaccoLicenseConsistencyReviewUseCase:
    name = "tobacco_license_consistency_review"
    version = "v1"
    ruleset_version = "tobacco-license-consistency-rules-v1-placeholder"
    supported_document_types = (
        "tobacco_license_consistency_review",
        "tobacco_license_consistency",
        "business_license",
        "tobacco_license",
    )

    def supports(self, input_context: ReviewInputContext) -> bool:
        return input_context.input.declared_document_type in self.supported_document_types

    def review(self, input_context: ReviewInputContext) -> ReviewResult:
        now = datetime.now(ZoneInfo(settings.timezone))
        workflow_result = run_tobacco_license_workflow(input_context)
        return ReviewResult.model_validate(
            {
                "task_id": input_context.task_id,
                "use_case_name": self.name,
                "use_case_version": self.version,
                "skill_name": self.name,
                "skill_version": self.version,
                "ruleset_version": self.ruleset_version,
                "capability_names": [],
                "document_type": input_context.input.declared_document_type
                or "tobacco_license_consistency",
                "status": ReviewStatus.PENDING_MANUAL_REVIEW,
                "risk_level": RiskLevel.MEDIUM,
                "needs_manual_review": True,
                "rule_results": [],
                "summary": (
                    "tobacco_license_consistency_review 仅为多 Skill 架构占位，"
                    "尚未执行业务审核。"
                ),
                "manual_review": ManualReview(
                    status=ManualReviewStatus.PENDING,
                    reasons=[
                        "tobacco_license_consistency_review Runtime 尚未实现，需要人工复核"
                    ],
                ),
                "audit_events": [
                    AuditEvent(
                        event_type="tobacco_license_consistency_review.placeholder",
                        message=(
                            "tobacco_license_consistency_review 占位 Skill "
                            "已返回未实现状态"
                        ),
                        occurred_at=now,
                    )
                ],
                "created_at": now,
                "updated_at": now,
                "skill_result": workflow_result,
            }
        )


tobacco_license_consistency_review_use_case = (
    TobaccoLicenseConsistencyReviewUseCase()
)
