import json

from langchain_core.language_models.fake import FakeListLLM

from app.skills.food_license.extractors import (
    build_llm_structured_extraction_chain,
    extract_food_license_fields,
)


OCR_TEXT = "食品经营许可证\n经营者名称：成都示例食品有限公司\n统一社会信用代码：91510100MA00000000\n许可证编号：JY15101000000000\n经营项目：预包装食品销售\n有效期至：2099-01-01"


def test_llm_enabled_uses_fake_llm_to_extract_fields():
    fake_llm = FakeListLLM(
        responses=[
            json.dumps(
                {
                    "subject_name": "成都示例食品有限公司",
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
        OCR_TEXT,
        llm_enabled=True,
        llm_chain=chain,
    )

    assert result.fields.subject_name == "成都示例食品有限公司"
    assert result.fields.credit_code == "91510100MA00000000"
    assert result.fields.license_no == "JY15101000000000"
    assert result.metadata["extraction_mode"] == "llm"
    assert result.metadata["fallback_used"] is False


def test_llm_parse_failure_falls_back_to_regex():
    fake_llm = FakeListLLM(responses=["不是 JSON"])
    chain = build_llm_structured_extraction_chain(fake_llm)

    result = extract_food_license_fields(
        OCR_TEXT,
        llm_enabled=True,
        llm_chain=chain,
    )

    assert result.fields.license_no == "JY15101000000000"
    assert result.metadata["extraction_mode"] == "fallback"
    assert result.metadata["fallback_used"] is True
    assert result.metadata["fallback_reason"] == "llm_error"


def test_llm_not_configured_does_not_call_real_llm_and_falls_back(monkeypatch):
    monkeypatch.delenv("FOOD_LICENSE_LLM_API_KEY", raising=False)
    monkeypatch.setenv("FOOD_LICENSE_LLM_ENABLED", "true")

    result = extract_food_license_fields(OCR_TEXT)

    assert result.fields.license_no == "JY15101000000000"
    assert result.metadata["extraction_mode"] == "fallback"
    assert result.metadata["fallback_used"] is True
    assert result.metadata["fallback_reason"] == "llm_not_configured"
