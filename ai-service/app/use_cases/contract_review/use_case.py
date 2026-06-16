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
from app.workflows.contract import run_contract_workflow


class ContractReviewUseCase:
    name = "contract_review"
    version = "v1"
    ruleset_version = "contract-rules-v1-placeholder"
    supported_document_types = (
        "contract_review",
        "contract",
        "lease_contract",
        "food_supply_contract",
    )

    def supports(self, input_context: ReviewInputContext) -> bool:
        return input_context.input.declared_document_type in self.supported_document_types

    def review(self, input_context: ReviewInputContext) -> ReviewResult:
        now = datetime.now(ZoneInfo(settings.timezone))
        workflow_result = run_contract_workflow(input_context)
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
                or "contract",
                "status": ReviewStatus.PENDING_MANUAL_REVIEW,
                "risk_level": RiskLevel.MEDIUM,
                "needs_manual_review": True,
                "rule_results": [],
                "summary": "contract_review 仅为 use_case 架构占位，尚未执行业务审核。",
                "manual_review": ManualReview(
                    status=ManualReviewStatus.PENDING,
                    reasons=["contract_review use_case 尚未实现，需要人工复核"],
                ),
                "audit_events": [
                    AuditEvent(
                        event_type="contract_review.placeholder",
                        message="contract_review 占位 use_case 已返回未实现状态",
                        occurred_at=now,
                    )
                ],
                "created_at": now,
                "updated_at": now,
                "skill_result": workflow_result,
            }
        )


contract_review_use_case = ContractReviewUseCase()
