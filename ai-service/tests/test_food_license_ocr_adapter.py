from app.tools.food_license_ocr_adapter import (
    FoodLicenseOcrTextParser,
    QwenOcrFoodLicenseAdapter,
    QwenOcrWithAliyunFallbackFoodLicenseAdapter,
    validate_food_license_ocr_result,
)
from app.tools.vision_adapter import VisionInput


class StubAdapter:
    implementation_status = "configured"

    def __init__(self, result):
        self.result = result
        self.calls = []

    def extract_text(self, source):
        self.calls.append(source)
        return self.result


def test_validate_food_license_ocr_result_accepts_key_fields():
    validation = validate_food_license_ocr_result(
        {
            "structured_fields": {
                "document_type": "food_license",
                "subject_name": "成都市聚和盛供应链管理有限公司",
                "credit_code": "91510105MA6BCUKR3A",
                "license_no": "JY15101050167261",
            },
            "metadata": {},
        }
    )

    assert validation == {"passed": True, "failure_reasons": []}


def test_validate_food_license_ocr_result_rejects_business_serial_as_credit_code():
    validation = validate_food_license_ocr_result(
        {
            "structured_fields": {
                "document_type": "food_license",
                "subject_name": "成都市聚和盛供应链管理有限公司",
                "credit_code": "1001010427202311270017",
                "license_no": "JY15101050167261",
            },
            "metadata": {},
        }
    )

    assert validation == {
        "passed": False,
        "failure_reasons": ["credit_code_format_invalid"],
    }


def test_food_license_fallback_adapter_uses_qwen_result_when_validation_passes():
    primary = StubAdapter(
        {
            "text": "qwen text",
            "structured_fields": {
                "document_type": "food_license",
                "subject_name": "成都市聚和盛供应链管理有限公司",
                "credit_code": "91510105MA6BCUKR3A",
                "license_no": "JY15101050167261",
            },
            "metadata": {"provider": "qwen_ocr"},
        }
    )
    fallback = StubAdapter({"text": "fallback should not be called", "metadata": {}})

    result = QwenOcrWithAliyunFallbackFoodLicenseAdapter(
        primary_adapter=primary,
        fallback_adapter=fallback,
    ).extract_text({})

    assert result["text"] == "qwen text"
    assert fallback.calls == []
    assert result["metadata"]["fallback_used"] is False
    assert result["metadata"]["final_provider"] == "qwen_ocr"


def test_food_license_fallback_adapter_uses_aliyun_text_and_llm_when_qwen_has_no_fields():
    primary = StubAdapter(
        {
            "text": "",
            "metadata": {
                "provider": "qwen_ocr",
                "error_code": "QWEN_OCR_FOOD_LICENSE_PAGE_NOT_FOUND",
            },
        }
    )
    fallback = StubAdapter(
        {
            "text": "食品经营许可证\n经营者名称 成都市聚和盛供应链管理有限公司\n许可证编号 JY15101050167261",
            "metadata": {"provider": "aliyun_ocr_text"},
        }
    )
    parser = StubAdapter(
        {
            "text": "aliyun text",
            "structured_fields": {
                "document_type": "food_license",
                "subject_name": "成都市聚和盛供应链管理有限公司",
                "license_no": "JY15101050167261",
            },
            "metadata": {"provider": "aliyun_ocr_text_llm_parse"},
        }
    )

    result = QwenOcrWithAliyunFallbackFoodLicenseAdapter(
        primary_adapter=primary,
        fallback_adapter=fallback,
        fallback_text_parser=parser,
    ).extract_text({"content": b"fake"})

    assert result["text"] == "aliyun text"
    assert len(fallback.calls) == 1
    assert len(parser.calls) == 1
    assert result["metadata"]["provider"] == "qwen_ocr_with_aliyun_fallback"
    assert result["metadata"]["final_provider"] == "aliyun_ocr_text_llm_parse"
    assert result["metadata"]["fallback_used"] is True
    assert result["metadata"]["fallback_trigger"] == "QWEN_OCR_FOOD_LICENSE_PAGE_NOT_FOUND"
    assert result["metadata"]["fallback_ocr_summary"]["provider"] == "aliyun_ocr_text"


def test_food_license_ocr_text_parser_uses_license_prompt(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = {}

    class StubMessage:
        content = (
            '{"document_type":"食品经营许可证",'
            '"subject_name":"成都市聚和盛供应链管理有限公司",'
            '"license_no":"JY15101050167261",'
            '"business_items":["预包装食品销售"]}'
        )

    class StubChoice:
        message = StubMessage()

    class StubResponse:
        choices = [StubChoice()]

    class StubCompletions:
        def create(self, **kwargs):
            calls.update(kwargs)
            return StubResponse()

    class StubChat:
        completions = StubCompletions()

    class StubOpenAI:
        def __init__(self, **kwargs):
            calls["client"] = kwargs
            self.chat = StubChat()

    import app.tools.food_license_ocr_adapter as food_license_ocr_adapter

    monkeypatch.setattr(food_license_ocr_adapter, "OpenAI", StubOpenAI, raising=False)
    parser = FoodLicenseOcrTextParser(model="qwen-flash", base_url="https://example.test/v1")

    result = parser.extract_text(
        {
            "text": "食品经营许可证\n经营者名称 成都市聚和盛供应链管理有限公司\n许可证编号 JY15101050167261",
            "metadata": {"provider": "aliyun_ocr_text"},
        }
    )

    assert result["structured_fields"]["document_type"] == "food_license"
    assert result["structured_fields"]["license_no"] == "JY15101050167261"
    assert result["metadata"]["provider"] == "aliyun_ocr_text_llm_parse"
    prompt = calls["messages"][0]["content"][0]["text"]
    assert "# Skill: food-license-review" in prompt
    assert "字段抽取要求" in prompt
    assert "不要把许可证编号" in prompt


def test_qwen_food_license_adapter_calls_openai_compatible_multimodal_api(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = {}

    class StubMessage:
        content = (
            '{"document_type":"食品经营许可证",'
            '"subject_name":"成都市聚和盛供应链管理有限公司",'
            '"credit_code":"91510105MA6BCUKR3A",'
            '"license_no":"JY15101050167261"}'
        )

    class StubChoice:
        message = StubMessage()

    class StubResponse:
        choices = [StubChoice()]

    class StubCompletions:
        def create(self, **kwargs):
            calls.update(kwargs)
            return StubResponse()

    class StubChat:
        completions = StubCompletions()

    class StubOpenAI:
        def __init__(self, **kwargs):
            calls["client"] = kwargs
            self.chat = StubChat()

    import app.tools.food_license_ocr_adapter as food_license_ocr_adapter

    monkeypatch.setattr(food_license_ocr_adapter, "OpenAI", StubOpenAI, raising=False)
    adapter = QwenOcrFoodLicenseAdapter(model="qwen3.5-ocr", base_url="https://example.test/v1")

    result = adapter.extract_text(
        VisionInput(
            content=b"fake-jpg",
            mime_type="image/jpeg",
            file_name="food-license.jpg",
        )
    )

    assert result["structured_fields"]["document_type"] == "food_license"
    assert result["structured_fields"]["subject_name"] == "成都市聚和盛供应链管理有限公司"
    assert result["structured_fields"]["license_no"] == "JY15101050167261"
    assert result["metadata"]["provider"] == "qwen_ocr"
    assert result["metadata"]["selected_page"] == 1
    assert calls["model"] == "qwen3.5-ocr"
    prompt = calls["messages"][0]["content"][0]["text"]
    assert "# Skill: food-license-review" in prompt
    assert "食品经营许可证" in prompt
