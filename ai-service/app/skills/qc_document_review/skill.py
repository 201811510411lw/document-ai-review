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
from app.workflows.qc_document import run_qc_document_workflow


class QcDocumentReviewSkill:
    name = "qc_document_review"
    version = "v1"
    ruleset_version = "qc-document-rules-v1-placeholder"
    supported_document_types = (
        "qc_document_review",
        "qc_document",
        "business_license",
        "food_license",
        "food_production_license",
        "batch_report",
        "third_party_inspection_report",
    )

    def supports(self, input_context: ReviewInputContext) -> bool:
        return input_context.input.declared_document_type in self.supported_document_types

    def review(self, input_context: ReviewInputContext) -> ReviewResult:
        now = datetime.now(ZoneInfo(settings.timezone))
        workflow_result = run_qc_document_workflow(input_context)
        return ReviewResult.model_validate(
            {
                "task_id": input_context.task_id,
                "skill_name": self.name,
                "skill_version": self.version,
                "ruleset_version": self.ruleset_version,
                "document_type": input_context.input.declared_document_type
                or "qc_document",
                "status": ReviewStatus.PENDING_MANUAL_REVIEW,
                "risk_level": RiskLevel.MEDIUM,
                "needs_manual_review": True,
                "rule_results": [],
                "summary": "qc_document_review 仅为多 Skill 架构占位，尚未执行业务审核。",
                "manual_review": ManualReview(
                    status=ManualReviewStatus.PENDING,
                    reasons=["qc_document_review Runtime 尚未实现，需要人工复核"],
                ),
                "audit_events": [
                    AuditEvent(
                        event_type="qc_document_review.placeholder",
                        message="qc_document_review 占位 Skill 已返回未实现状态",
                        occurred_at=now,
                    )
                ],
                "created_at": now,
                "updated_at": now,
                "skill_result": workflow_result,
            }
        )


qc_document_review_skill = QcDocumentReviewSkill()
