import json

from langchain_core.language_models.fake import FakeListLLM
from langchain_core.runnables import RunnableLambda

from app.skills.food_license.extractors import (
    build_llm_structured_extraction_chain,
    extract_food_license_fields,
)
from app.skills.food_license.models import FoodLicenseExtractedFields


OCR_TEXT = "食品经营许可证\n经营者名称：成都示例食品有限公司\n统一社会信用代码：91510100MA00000000\n许可证编号：JY15101000000000\n经营项目：预包装食品销售\n有效期至：2099-01-01"


def test_complete_regex_fields_skip_llm():
    calls = []
    extractor = RunnableLambda(lambda payload: calls.append(payload))

    result = extract_food_license_fields(
        OCR_TEXT,
        llm_enabled=True,
        llm_chain=extractor,
    )

    assert calls == []
    assert result.fields.credit_code == "91510100MA00000000"
    assert result.fields.license_no == "JY15101000000000"
    assert result.metadata["extraction_mode"] == "regex_only"
    assert result.metadata["llm_used"] is False


def test_missing_regex_fields_use_fake_llm_to_supplement_only_missing_fields():
    fake_llm = FakeListLLM(
        responses=[
            json.dumps(
                {
                    "subject_name": "LLM 不应覆盖正则主体名称",
                    "credit_code": "91510100MA00000000",
                    "license_no": "JY15101000000000",
                    "business_items": ["预包装食品销售"],
                    "valid_to": "2099-01-01",
                },
                ensure_ascii=False,
            )
        ]
    )
    chain = build_llm_structured_extraction_chain(fake_llm)

    result = extract_food_license_fields(
        "食品经营许可证\n经营者名称：成都示例食品有限公司\n许可证编号：JY15101000000000",
        llm_enabled=True,
        llm_chain=chain,
    )

    assert result.fields.subject_name == "成都示例食品有限公司"
    assert result.fields.credit_code == "91510100MA00000000"
    assert result.fields.license_no == "JY15101000000000"
    assert result.fields.business_items == ["预包装食品销售"]
    assert result.metadata["extraction_mode"] == "regex_with_llm_supplement"
    assert result.metadata["llm_used"] is True


def test_llm_parse_failure_falls_back_to_regex():
    fake_llm = FakeListLLM(responses=["不是 JSON"])
    chain = build_llm_structured_extraction_chain(fake_llm)

    result = extract_food_license_fields(
        "食品经营许可证\n经营者名称：成都示例食品有限公司\n许可证编号：JY15101000000000",
        llm_enabled=True,
        llm_chain=chain,
    )

    assert result.fields.license_no == "JY15101000000000"
    assert result.fields.credit_code is None
    assert result.metadata["extraction_mode"] == "regex_fallback_after_llm_failed"
    assert result.metadata["llm_used"] is False
    assert result.metadata["llm_reason"] == "llm_error"


def test_llm_not_configured_does_not_call_real_llm_and_falls_back(monkeypatch):
    monkeypatch.delenv("FOOD_LICENSE_LLM_API_KEY", raising=False)
    monkeypatch.setenv("FOOD_LICENSE_LLM_ENABLED", "true")

    result = extract_food_license_fields(
        "食品经营许可证\n经营者名称：成都示例食品有限公司\n许可证编号：JY15101000000000"
    )

    assert result.fields.license_no == "JY15101000000000"
    assert result.metadata["extraction_mode"] == "regex_fallback_after_llm_failed"
    assert result.metadata["llm_used"] is False
    assert result.metadata["llm_reason"] == "llm_not_configured"


def test_llm_supplement_does_not_overwrite_stable_regex_required_fields():
    result = extract_food_license_fields(
        "食品经营许可证\n统一社会信用代码：91510100MA00000000",
        llm_enabled=True,
        llm_chain=RunnableLambda(
            lambda _: FoodLicenseExtractedFields(
                credit_code="91510100MA99999999",
                license_no="JY15101000000000",
            )
        ),
    )

    assert result.fields.credit_code == "91510100MA00000000"
    assert result.fields.license_no == "JY15101000000000"
    assert result.metadata["extraction_mode"] == "regex_with_llm_supplement"
