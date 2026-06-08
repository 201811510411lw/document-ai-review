from app.models import (
    ManualReviewStatus,
    ReviewInput,
    ReviewInputContext,
    ReviewResult,
    ReviewStatus,
    RiskLevel,
    RuleResult,
)
from app.skills.food_license.nodes import (
    classify_document,
    load_document,
    route_review,
    summarize_risk,
)
from app.skills.food_license.models import FoodLicenseDocumentClassification
from app.skills.food_license.skill import food_license_skill


def test_food_license_review_runs_internal_workflow_and_returns_review_result():
    input_context = ReviewInputContext(
        task_id="review-task-001",
        input=ReviewInput(
            ocr_text="食品经营许可证\n经营者名称：成都示例食品有限公司\n许可证编号：JY15101000000000",
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_license",
        ),
        skill_name="food_license",
        skill_version="v1",
        ruleset_version="food-license-rules-v1",
    )

    result = food_license_skill.review(input_context)
    payload = result.model_dump(mode="json")

    assert isinstance(result, ReviewResult)
    assert result.task_id == "review-task-001"
    assert result.skill_name == "food_license"
    assert result.skill_version == "v1"
    assert result.ruleset_version == "food-license-rules-v1"
    assert result.document_type == "food_license"
    assert result.status == ReviewStatus.REVIEWED
    assert result.risk_level == RiskLevel.NONE
    assert result.needs_manual_review is False
    assert result.manual_review.status == ManualReviewStatus.NOT_REQUIRED
    assert result.audit_events

    assert "extracted_fields" not in payload
    assert "normalized_fields" not in payload
    assert "document_classification" not in payload
    assert payload["skill_result"]["document_classification"] == {
        "document_type": "food_license",
        "confidence": 1.0,
        "reasons": ["OCR 文本包含食品经营许可证特征"],
    }
    assert payload["skill_result"]["extracted_fields"]["license_no"] is None
    assert payload["skill_result"]["normalized_fields"]["license_no"] is None


def test_load_document_standardizes_ocr_text_into_workflow_state():
    input_context = ReviewInputContext(
        task_id="review-task-001",
        input=ReviewInput(
            ocr_text="  食品经营许可证\n许可证编号：JY15101000000000  ",
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
        ),
        skill_name="food_license",
        skill_version="v1",
        ruleset_version="food-license-rules-v1",
    )

    state = load_document({"input_context": input_context})

    assert state["document_text"] == "食品经营许可证\n许可证编号：JY15101000000000"


def test_classify_document_marks_non_food_license_text_as_unknown():
    state = classify_document({"document_text": "营业执照\n统一社会信用代码：91510100MA00000000"})

    assert state["document_classification"].document_type == "unknown"
    assert state["document_classification"].confidence == 0.0


def test_summarize_risk_uses_rule_results_without_llm_decision():
    state = summarize_risk(
        {
            "rule_results": [
                RuleResult(
                    rule_code="SUBJECT_NAME_MATCH",
                    rule_name="主体名称是否一致",
                    passed=False,
                    risk_level_on_failure=RiskLevel.MEDIUM,
                    message="主体名称不一致",
                )
            ]
        }
    )

    assert state["risk_level"] == RiskLevel.MEDIUM
    assert state["summary"] == "发现确定性规则风险。"


def test_route_review_sets_manual_review_from_risk_level():
    state = route_review(
        {
            "document_classification": FoodLicenseDocumentClassification(
                document_type="food_license"
            ),
            "risk_level": RiskLevel.MEDIUM,
        }
    )

    assert state["needs_manual_review"] is True
    assert state["manual_review"].status == ManualReviewStatus.PENDING
    assert state["manual_review"].reasons == ["确定性规则结果需要人工复核"]


def test_unknown_document_type_requires_manual_review():
    input_context = ReviewInputContext(
        task_id="review-task-unknown",
        input=ReviewInput(
            ocr_text="营业执照\n统一社会信用代码：91510100MA00000000",
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_license",
        ),
        skill_name="food_license",
        skill_version="v1",
        ruleset_version="food-license-rules-v1",
    )

    result = food_license_skill.review(input_context)
    payload = result.model_dump(mode="json")

    assert payload["skill_result"]["document_classification"]["document_type"] == "unknown"
    assert result.risk_level == RiskLevel.NONE
    assert result.needs_manual_review is True
    assert result.manual_review.status == ManualReviewStatus.PENDING
    assert result.manual_review.reasons == ["文档类型无法识别，需要人工复核"]
