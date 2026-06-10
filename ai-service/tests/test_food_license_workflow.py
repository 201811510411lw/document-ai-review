from app.models import (
    ManualReviewStatus,
    ReviewInput,
    ReviewInputContext,
    ReviewResult,
    ReviewStatus,
    RiskLevel,
)
from app.use_cases.food_license.use_case import food_license_use_case
from app.workflows.food_license import run_food_license_workflow


def test_food_license_use_case_review_extracts_fields_and_returns_review_result():
    input_context = ReviewInputContext(
        task_id="review-task-001",
        input=ReviewInput(
            ocr_text=(
                "食品经营许可证\n"
                "经营者名称：成都示例食品有限公司\n"
                "统一社会信用代码：91510100MA00000000\n"
                "许可证编号：JY15101000000000\n"
                "经营项目：预包装食品销售、散装食品销售\n"
                "有效期至：2028年06月05日"
            ),
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_license",
        ),
        skill_name="food_license",
        skill_version="v1",
        ruleset_version="food-license-rules-v1",
    )

    result = food_license_use_case.review(input_context)
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
    extracted_fields = payload["skill_result"]["extracted_fields"]
    normalized_fields = payload["skill_result"]["normalized_fields"]
    assert extracted_fields["subject_name"] == "成都示例食品有限公司"
    assert extracted_fields["credit_code"] == "91510100MA00000000"
    assert extracted_fields["license_no"] == "JY15101000000000"
    assert extracted_fields["business_items"] == ["预包装食品销售", "散装食品销售"]
    assert extracted_fields["valid_to"] == "2028-06-05"
    assert normalized_fields["license_no"] == "JY15101000000000"
    assert payload["rule_results"][0]["rule_code"] == "FOOD_LICENSE_RULE_ENGINE_STUB"


def test_food_license_workflow_public_entrypoint_runs_stub_rule_executor():
    input_context = ReviewInputContext(
        task_id="review-task-rules",
        input=ReviewInput(
            ocr_text=(
                "食品经营许可证\n"
                "经营者名称：成都示例食品有限公司\n"
                "统一社会信用代码：91510100MA00000000\n"
                "许可证编号：JY15101000000000\n"
                "经营项目：预包装食品销售、散装食品销售\n"
                "有效期至：2028年06月05日"
            ),
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_license",
        ),
        skill_name="food_license",
        skill_version="v1",
        ruleset_version="food-license-rules-v1",
    )

    state = run_food_license_workflow(input_context)

    assert len(state["rule_results"]) == 5
    assert state["rule_results"][0].rule_code == "FOOD_LICENSE_RULE_ENGINE_STUB"
    assert [rule_result.rule_code for rule_result in state["rule_results"]] == [
        "FOOD_LICENSE_RULE_ENGINE_STUB",
        "FOOD_LICENSE_TYPE_MATCH",
        "FOOD_LICENSE_SUBJECT_NAME_MATCH",
        "FOOD_LICENSE_CREDIT_CODE_MATCH",
        "FOOD_LICENSE_VALIDITY_PERIOD",
    ]
    assert all(rule_result.passed is True for rule_result in state["rule_results"])
    assert state["rule_execution"].risk_level == RiskLevel.NONE
    assert state["rule_execution"].needs_manual_review is False


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

    result = food_license_use_case.review(input_context)
    payload = result.model_dump(mode="json")

    assert payload["skill_result"]["document_classification"]["document_type"] == "unknown"
    assert result.risk_level == RiskLevel.HIGH
    assert result.needs_manual_review is True
    assert result.manual_review.status == ManualReviewStatus.PENDING
    assert result.manual_review.reasons == ["文档类型无法识别，需要人工复核"]
    assert payload["rule_results"][1]["rule_code"] == "FOOD_LICENSE_TYPE_MATCH"
    assert payload["rule_results"][1]["passed"] is False
