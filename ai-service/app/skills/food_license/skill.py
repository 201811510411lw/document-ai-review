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
from app.skills.food_license.models import (
    FoodLicenseDocumentClassification,
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
        skill_result = FoodLicenseSkillResult(
            document_classification=FoodLicenseDocumentClassification(
                document_type="food_license",
                confidence=None,
                reasons=["OCR 文本已进入 food_license 快捷审核边界"],
            )
        )

        return ReviewResult(
            task_id=input_context.task_id,
            skill_name=self.name,
            skill_version=self.version,
            ruleset_version=self.ruleset_version,
            document_type="food_license",
            status=ReviewStatus.REVIEWED,
            risk_level=RiskLevel.NONE,
            needs_manual_review=False,
            rule_results=[],
            summary="已接收 OCR 文本并完成 food_license 快捷审核占位处理。",
            manual_review=ManualReview(status=ManualReviewStatus.NOT_REQUIRED),
            audit_events=[
                AuditEvent(
                    event_type="food_license.review.placeholder_completed",
                    message="food_license 快捷审核占位处理完成",
                    occurred_at=now,
                )
            ],
            created_at=now,
            updated_at=now,
            skill_result=skill_result,
        )


food_license_skill = FoodLicenseSkill()
