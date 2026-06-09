from app.models import ManualReviewStatus, ReviewInput, ReviewInputContext, ReviewStatus
from app.skills.registry import skill_registry


def test_placeholder_skills_return_clear_not_implemented_result():
    for skill_name, declared_document_type in [
        ("qc_document_review", "qc_document_review"),
        ("tobacco_license_consistency_review", "tobacco_license_consistency_review"),
        ("contract_review", "contract_review"),
    ]:
        skill = skill_registry.get(skill_name)
        input_context = ReviewInputContext(
            task_id=f"review-task-{skill_name}",
            input=ReviewInput(
                ocr_text="占位输入",
                supplier_name="成都示例食品有限公司",
                supplier_credit_code="91510100MA00000000",
                declared_document_type=declared_document_type,
            ),
            skill_name=skill.name,
            skill_version=skill.version,
            ruleset_version=skill.ruleset_version,
        )

        result = skill.review(input_context)
        payload = result.model_dump(mode="json")

        assert result.status == ReviewStatus.PENDING_MANUAL_REVIEW
        assert result.needs_manual_review is True
        assert result.manual_review.status == ManualReviewStatus.PENDING
        assert payload["skill_result"]["implementation_status"] == "not_implemented"
        assert "尚未执行业务审核" in result.summary
