from app.models import ReviewInput, ReviewInputContext, RiskLevel
from app.skills.food_license.extractor import extract_food_license_fields
from app.workflows.food_license import nodes as food_license_nodes
from app.workflows.food_license import run_food_license_workflow


class CountingLlmAdapter:
    def __init__(self, completion: dict | None = None, should_raise: bool = False) -> None:
        self.calls = []
        self.completion = completion or {}
        self.should_raise = should_raise

    def complete_missing_fields(self, *, document_text, extracted_fields, missing_fields):
        self.calls.append(
            {
                "document_text": document_text,
                "extracted_fields": extracted_fields,
                "missing_fields": missing_fields,
            }
        )
        if self.should_raise:
            raise RuntimeError("stub llm failed")
        return self.completion


def test_llm_stub_is_not_called_when_regex_fields_are_complete():
    llm = CountingLlmAdapter()

    fields, metadata = extract_food_license_fields(
        "食品经营许可证\n"
        "经营者名称：成都示例食品有限公司\n"
        "统一社会信用代码：91510100MA00000000\n"
        "许可证编号：JY15101000000000\n"
        "经营项目：预包装食品销售、散装食品销售\n"
        "有效期至：2028年06月05日",
        llm_adapter=llm,
    )

    assert llm.calls == []
    assert fields.license_no == "JY15101000000000"
    assert metadata["llm_used"] is False


def test_llm_stub_supplements_missing_fields_without_overriding_regex_fields():
    llm = CountingLlmAdapter(
        {
            "subject_name": "LLM 不应覆盖名称",
            "credit_code": "91510100MA22222222",
            "business_items": ["保健食品销售"],
            "valid_to": "2028-05-31",
        }
    )

    fields, metadata = extract_food_license_fields(
        "食品经营许可证\n"
        "名称 成都测试商贸有限公司\n"
        "编号 JY15101001111111",
        llm_adapter=llm,
    )

    assert len(llm.calls) == 1
    assert fields.subject_name == "成都测试商贸有限公司"
    assert fields.license_no == "JY15101001111111"
    assert fields.credit_code == "91510100MA22222222"
    assert fields.business_items == ["保健食品销售"]
    assert fields.valid_to == "2028-05-31"
    assert metadata["llm_used"] is True


def test_llm_stub_exception_falls_back_to_regex_fields():
    llm = CountingLlmAdapter(should_raise=True)

    fields, metadata = extract_food_license_fields(
        "食品经营许可证\n"
        "名称 成都测试商贸有限公司\n"
        "编号 JY15101001111111",
        llm_adapter=llm,
    )

    assert fields.subject_name == "成都测试商贸有限公司"
    assert fields.license_no == "JY15101001111111"
    assert fields.credit_code is None
    assert metadata["llm_used"] is True
    assert metadata["llm_error"] == "RuntimeError"


def test_llm_supplement_does_not_decide_risk_level(monkeypatch):
    llm = CountingLlmAdapter(
        {
            "risk_level": "HIGH",
            "credit_code": "91510100MA22222222",
            "business_items": ["预包装食品销售"],
            "valid_to": "2028-05-31",
        }
    )
    monkeypatch.setattr(food_license_nodes, "food_license_llm_adapter", llm)

    state = run_food_license_workflow(
        ReviewInputContext(
            task_id="review-task-llm-risk",
            input=ReviewInput(
                ocr_text="食品经营许可证\n名称 成都测试商贸有限公司\n编号 JY15101001111111",
                supplier_name="成都测试商贸有限公司",
                supplier_credit_code="91510100MA22222222",
                declared_document_type="food_license",
            ),
            skill_name="food_license",
            skill_version="v1",
            ruleset_version="food-license-rules-v1",
        )
    )

    assert len(llm.calls) == 1
    assert state["risk_level"] == RiskLevel.NONE
    assert state["rule_results"][0].rule_code == "FOOD_LICENSE_RULE_ENGINE_STUB"
    assert all(rule_result.passed is True for rule_result in state["rule_results"])
