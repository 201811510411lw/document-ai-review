from datetime import datetime, timezone

from app.models import (
    ManualReview,
    ManualReviewStatus,
    ReviewInput,
    ReviewInputContext,
    ReviewResult,
    ReviewStatus,
    RiskLevel,
)
from app.skills.registry import SkillRegistry, skill_registry


class StubSkill:
    def __init__(self, name: str, supported_document_types: tuple[str, ...]) -> None:
        self.name = name
        self.version = "v1"
        self.ruleset_version = f"{name}-rules-v1"
        self.supported_document_types = supported_document_types

    def supports(self, input_context: ReviewInputContext) -> bool:
        return input_context.input.declared_document_type in self.supported_document_types

    def review(self, input_context: ReviewInputContext) -> ReviewResult:
        now = datetime(2026, 6, 8, 14, 30, tzinfo=timezone.utc)
        return ReviewResult(
            task_id=input_context.task_id,
            skill_name=self.name,
            skill_version=self.version,
            ruleset_version=self.ruleset_version,
            document_type=input_context.input.declared_document_type or self.name,
            status=ReviewStatus.PENDING_MANUAL_REVIEW,
            risk_level=RiskLevel.MEDIUM,
            needs_manual_review=True,
            rule_results=[],
            summary="stub",
            manual_review=ManualReview(status=ManualReviewStatus.PENDING),
            audit_events=[],
            created_at=now,
            updated_at=now,
            skill_result={"implementation_status": "not_implemented"},
        )


def test_skill_registry_can_register_and_select_multiple_skills():
    registry = SkillRegistry()
    contract_skill = StubSkill("contract_review", ("contract_review",))
    qc_skill = StubSkill("qc_document_review", ("qc_document_review",))
    registry.register(contract_skill)
    registry.register(qc_skill)

    input_context = ReviewInputContext(
        task_id="review-task-001",
        input=ReviewInput(
            ocr_text="合同文本",
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="contract_review",
        ),
        skill_name="",
        skill_version="",
        ruleset_version="",
    )

    assert registry.list() == [contract_skill, qc_skill]
    assert registry.get("contract_review") is contract_skill
    assert registry.select(input_context) is contract_skill


def test_global_skill_registry_keeps_food_license_and_placeholders():
    skill_names = {skill.name for skill in skill_registry.list()}

    assert skill_registry.get("food_license").name == "food_license"
    assert {
        "food_license",
        "qc_document_review",
        "tobacco_license_consistency_review",
        "contract_review",
    }.issubset(skill_names)
