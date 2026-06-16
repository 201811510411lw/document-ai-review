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


class QcDocumentReviewUseCase:
    name = "qc_document_review"
    version = "v1"
    ruleset_version = "qc-document-rules-v1"
    supported_document_types = (
        "qc_document_review",
        "qc_document",
        "business_license",
        "food_license",
        "food_production_license",
        "batch_report",
        "third_party_inspection_report",
        "product_report",
    )

    def supports(self, input_context: ReviewInputContext) -> bool:
        return input_context.input.declared_document_type in self.supported_document_types

    def review(self, input_context: ReviewInputContext) -> ReviewResult:
        now = datetime.now(ZoneInfo(settings.timezone))
        workflow_result = run_qc_document_workflow(input_context)
        return ReviewResult.model_validate(
            {
                "task_id": input_context.task_id,
                "use_case_name": self.name,
                "use_case_version": self.version,
                "skill_name": self.name,
                "skill_version": self.version,
                "ruleset_version": self.ruleset_version,
                "capability_names": workflow_result.get("capability_names", []),
                "document_type": workflow_result.get("document_type")
                or input_context.input.declared_document_type
                or "qc_document",
                "status": workflow_result.get("status", ReviewStatus.PENDING_MANUAL_REVIEW),
                "risk_level": workflow_result.get("risk_level", RiskLevel.MEDIUM),
                "needs_manual_review": workflow_result.get("needs_manual_review", True),
                "rule_results": workflow_result.get("rule_results", []),
                "summary": workflow_result.get(
                    "summary",
                    "qc_document_review 返回了未完整的审核结果。",
                ),
                "manual_review": workflow_result.get(
                    "manual_review",
                    ManualReview(
                        status=ManualReviewStatus.PENDING,
                        reasons=["qc_document_review 未返回 manual_review，已回退人工复核"],
                    ),
                ),
                "audit_events": [
                    AuditEvent(
                        event_type="qc_document_review.workflow.completed",
                        message="qc_document_review 首期产品报告工作流执行完成",
                        occurred_at=now,
                    )
                ],
                "created_at": now,
                "updated_at": now,
                "skill_result": workflow_result.get("skill_result", workflow_result),
            }
        )


qc_document_review_use_case = QcDocumentReviewUseCase()
