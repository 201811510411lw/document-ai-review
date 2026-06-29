from app.tools.food_production_license_ocr_adapter import (
    FoodProductionLicenseOcrTextParser,
    QwenOcrFoodProductionLicenseAdapter,
    QwenOcrWithAliyunFallbackFoodProductionLicenseAdapter,
    validate_food_production_license_ocr_result,
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


def test_validate_food_production_license_ocr_result_accepts_key_fields():
    validation = validate_food_production_license_ocr_result(
        {
            "structured_fields": {
                "document_type": "food_production_license",
                "producer_name": "长沙波浪食品有限公司",
                "credit_code": "914301005617000000",
                "license_no": "SC12443010505553",
                "legal_person": "王波",
                "food_categories": ["糕点"],
            },
            "metadata": {},
        }
    )

    assert validation == {"passed": True, "failure_reasons": []}


def test_validate_food_production_license_ocr_result_rejects_serial_as_credit_code():
    validation = validate_food_production_license_ocr_result(
        {
            "structured_fields": {
                "document_type": "food_production_license",
                "producer_name": "长沙波浪食品有限公司",
                "credit_code": "1001010660202311270017",
                "license_no": "SC12443010505553",
                "legal_person": "王波",
                "food_categories": ["糕点"],
            },
            "metadata": {},
        }
    )

    assert validation == {
        "passed": False,
        "failure_reasons": ["credit_code_format_invalid"],
    }


def test_food_production_license_fallback_adapter_uses_qwen_result_when_validation_passes():
    primary = StubAdapter(
        {
            "text": "qwen text",
            "structured_fields": {
                "document_type": "food_production_license",
                "producer_name": "长沙波浪食品有限公司",
                "license_no": "SC12443010505553",
                "legal_person": "王波",
                "food_categories": ["糕点"],
            },
            "metadata": {"provider": "qwen_ocr"},
        }
    )
    fallback = StubAdapter({"text": "fallback should not be called", "metadata": {}})

    result = QwenOcrWithAliyunFallbackFoodProductionLicenseAdapter(
        primary_adapter=primary,
        fallback_adapter=fallback,
    ).extract_text({})

    assert result["text"] == "qwen text"
    assert fallback.calls == []
    assert result["metadata"]["fallback_used"] is False
    assert result["metadata"]["final_provider"] == "qwen_ocr"


def test_food_production_license_fallback_adapter_uses_aliyun_text_and_llm_when_qwen_has_no_fields():
    primary = StubAdapter(
        {
            "text": "",
            "metadata": {
                "provider": "qwen_ocr",
                "error_code": "QWEN_OCR_FOOD_PRODUCTION_LICENSE_PAGE_NOT_FOUND",
            },
        }
    )
    fallback = StubAdapter(
        {
            "text": "食品生产许可证\n生产者名称 长沙波浪食品有限公司\n许可证编号 SC12443010505553",
            "metadata": {"provider": "aliyun_ocr_text"},
        }
    )
    parser = StubAdapter(
        {
            "text": "aliyun text",
            "structured_fields": {
                "document_type": "food_production_license",
                "producer_name": "长沙波浪食品有限公司",
                "license_no": "SC12443010505553",
            },
            "metadata": {"provider": "aliyun_ocr_text_llm_parse"},
        }
    )

    result = QwenOcrWithAliyunFallbackFoodProductionLicenseAdapter(
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
    assert (
        result["metadata"]["fallback_trigger"]
        == "QWEN_OCR_FOOD_PRODUCTION_LICENSE_PAGE_NOT_FOUND"
    )
    assert result["metadata"]["fallback_ocr_summary"]["provider"] == "aliyun_ocr_text"


def test_food_production_license_fallback_adapter_uses_aliyun_text_when_legal_person_missing():
    primary = StubAdapter(
        {
            "text": "qwen text",
            "structured_fields": {
                "document_type": "food_production_license",
                "producer_name": "雅尚食品科技（广东）有限公司",
                "credit_code": "914405150766953478",
                "license_no": "SC11344051500589",
                "food_categories": ["糖果制品"],
            },
            "metadata": {"provider": "qwen_ocr"},
        }
    )
    fallback = StubAdapter(
        {
            "text": "食品生产许可证\n法 定 代 表 人 ： 沈 惠 超\n许可证编号 SC11344051500589",
            "metadata": {"provider": "aliyun_ocr_text"},
        }
    )
    parser = StubAdapter(
        {
            "text": "食品生产许可证\n法 定 代 表 人 ： 沈 惠 超\n许可证编号 SC11344051500589",
            "structured_fields": {
                "document_type": "food_production_license",
                "producer_name": "雅尚食品科技（广东）有限公司",
                "credit_code": "914405150766953478",
                "license_no": "SC11344051500589",
                "legal_person": "沈惠超",
                "food_categories": ["糖果制品"],
            },
            "metadata": {"provider": "aliyun_ocr_text_llm_parse"},
        }
    )

    result = QwenOcrWithAliyunFallbackFoodProductionLicenseAdapter(
        primary_adapter=primary,
        fallback_adapter=fallback,
        fallback_text_parser=parser,
    ).extract_text({"content": b"fake"})

    assert result["text"] == "qwen text"
    assert result["structured_fields"]["producer_name"] == "雅尚食品科技（广东）有限公司"
    assert result["structured_fields"]["legal_person"] == "沈惠超"
    assert result["metadata"]["fallback_used"] is True
    assert result["metadata"]["fallback_trigger"] == "legal_person_missing"
    assert result["metadata"]["final_provider"] == "qwen_ocr_with_aliyun_missing_field_merge"


def test_food_production_license_fallback_adapter_merges_food_categories_when_missing():
    primary = StubAdapter(
        {
            "text": "qwen text",
            "structured_fields": {
                "document_type": "food_production_license",
                "producer_name": "湖南省新林食品有限公司",
                "credit_code": "914306265702643586",
                "license_no": "SC12443062605105",
                "legal_person": "夏玲",
            },
            "metadata": {"provider": "qwen_ocr"},
        }
    )
    fallback = StubAdapter(
        {
            "text": "食品生产许可证\n食 品 类 别 ： 方 便 食 品\n许可证编号 SC12443062605105",
            "metadata": {"provider": "aliyun_ocr_text"},
        }
    )
    parser = StubAdapter(
        {
            "text": "食品生产许可证\n食 品 类 别 ： 方 便 食 品\n许可证编号 SC12443062605105",
            "structured_fields": {
                "document_type": "food_production_license",
                "producer_name": "湖南省新林食品有限公司",
                "credit_code": "914306265702643586",
                "license_no": "SC12443062605105",
                "legal_person": "夏玲",
                "food_categories": ["方便食品"],
            },
            "metadata": {"provider": "aliyun_ocr_text_llm_parse"},
        }
    )

    result = QwenOcrWithAliyunFallbackFoodProductionLicenseAdapter(
        primary_adapter=primary,
        fallback_adapter=fallback,
        fallback_text_parser=parser,
    ).extract_text({"content": b"fake"})

    assert result["text"] == "qwen text"
    assert result["structured_fields"]["producer_name"] == "湖南省新林食品有限公司"
    assert result["structured_fields"]["food_categories"] == ["方便食品"]
    assert result["metadata"]["fallback_used"] is True
    assert result["metadata"]["fallback_trigger"] == "food_categories_missing"
    assert result["metadata"]["final_provider"] == "qwen_ocr_with_aliyun_missing_field_merge"


def test_food_production_license_ocr_text_parser_uses_license_prompt(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = {}

    class StubMessage:
        content = (
            '{"document_type":"食品生产许可证",'
            '"producer_name":"长沙波浪食品有限公司",'
            '"license_no":"SC12443010505553",'
            '"food_categories":["糕点"]}'
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

    import app.tools.food_production_license_ocr_adapter as adapter_module

    monkeypatch.setattr(adapter_module, "OpenAI", StubOpenAI, raising=False)
    parser = FoodProductionLicenseOcrTextParser(
        model="qwen-flash",
        base_url="https://example.test/v1",
    )

    result = parser.extract_text(
        {
            "text": "食品生产许可证\n生产者名称 长沙波浪食品有限公司\n许可证编号 SC12443010505553",
            "metadata": {"provider": "aliyun_ocr_text"},
        }
    )

    assert result["structured_fields"]["document_type"] == "food_production_license"
    assert result["structured_fields"]["license_no"] == "SC12443010505553"
    assert result["metadata"]["provider"] == "aliyun_ocr_text_llm_parse"
    prompt = calls["messages"][0]["content"][0]["text"]
    assert "# Skill: food-production-license-review" in prompt
    assert "字段抽取要求" in prompt
    assert "不要把许可证编号" in prompt
    assert "输出要求" not in prompt
    assert "rule_results" not in prompt


def test_food_production_license_ocr_text_parser_extracts_legal_person_from_text(
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class StubMessage:
        content = (
            '{"document_type":"食品生产许可证",'
            '"producer_name":"雅尚食品科技（广东）有限公司",'
            '"credit_code":"914405150766953478",'
            '"license_no":"SC11344051500589"}'
        )

    class StubChoice:
        message = StubMessage()

    class StubResponse:
        choices = [StubChoice()]

    class StubCompletions:
        def create(self, **kwargs):
            return StubResponse()

    class StubChat:
        completions = StubCompletions()

    class StubOpenAI:
        def __init__(self, **kwargs):
            self.chat = StubChat()

    import app.tools.food_production_license_ocr_adapter as adapter_module

    monkeypatch.setattr(adapter_module, "OpenAI", StubOpenAI, raising=False)
    parser = FoodProductionLicenseOcrTextParser(model="qwen-flash")

    result = parser.extract_text(
        {
            "text": (
                "食品生产许可证\n"
                "生 产 者 名 称 ： 雅尚食品科技（广东）有限公司\n"
                "法 定 代 表 人 ： 沈 惠 超\n"
                "（ 负 责 人 ）\n"
                "住 所 ： 汕头市澄海区莲下镇南湾村莲南路北侧"
            ),
            "metadata": {"provider": "aliyun_ocr_text"},
        }
    )

    assert result["structured_fields"]["legal_person"] == "沈惠超"


def test_food_production_license_ocr_text_parser_extracts_food_categories_from_text(
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class StubMessage:
        content = (
            '{"document_type":"食品生产许可证",'
            '"producer_name":"湖南省新林食品有限公司",'
            '"credit_code":"914306265702643586",'
            '"license_no":"SC12443062605105",'
            '"legal_person":"夏玲"}'
        )

    class StubChoice:
        message = StubMessage()

    class StubResponse:
        choices = [StubChoice()]

    class StubCompletions:
        def create(self, **kwargs):
            return StubResponse()

    class StubChat:
        completions = StubCompletions()

    class StubOpenAI:
        def __init__(self, **kwargs):
            self.chat = StubChat()

    import app.tools.food_production_license_ocr_adapter as adapter_module

    monkeypatch.setattr(adapter_module, "OpenAI", StubOpenAI, raising=False)
    parser = FoodProductionLicenseOcrTextParser(model="qwen-flash")

    result = parser.extract_text(
        {
            "text": (
                "食品生产许可证\n"
                "生 产 地 址 ： 湖南省岳阳市平江县三阳乡金安村营济组\n"
                "食 品 类 别 ： 方 便 食 品\n"
                "发证机关：平江县市场监督管理局"
            ),
            "metadata": {"provider": "aliyun_ocr_text"},
        }
    )

    assert result["structured_fields"]["food_categories"] == ["方便食品"]


def test_food_production_license_ocr_text_parser_extracts_arbitrary_food_categories(
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class StubMessage:
        content = (
            '{"document_type":"食品生产许可证",'
            '"producer_name":"示例食品有限公司",'
            '"credit_code":"914306265702643586",'
            '"license_no":"SC12443062605105",'
            '"legal_person":"张三"}'
        )

    class StubChoice:
        message = StubMessage()

    class StubResponse:
        choices = [StubChoice()]

    class StubCompletions:
        def create(self, **kwargs):
            return StubResponse()

    class StubChat:
        completions = StubCompletions()

    class StubOpenAI:
        def __init__(self, **kwargs):
            self.chat = StubChat()

    import app.tools.food_production_license_ocr_adapter as adapter_module

    monkeypatch.setattr(adapter_module, "OpenAI", StubOpenAI, raising=False)
    parser = FoodProductionLicenseOcrTextParser(model="qwen-flash")

    result = parser.extract_text(
        {
            "text": (
                "食品生产许可证\n"
                "食 品 类 别 ： 糕 点 、 饮 料 ； 乳 制 品\n"
                "发证机关：示例市场监督管理局"
            ),
            "metadata": {"provider": "aliyun_ocr_text"},
        }
    )

    assert result["structured_fields"]["food_categories"] == [
        "糕点",
        "饮料",
        "乳制品",
    ]


def test_qwen_food_production_license_adapter_calls_openai_compatible_multimodal_api(
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = {}

    class StubMessage:
        content = (
            '{"document_type":"食品生产许可证",'
            '"producer_name":"长沙波浪食品有限公司",'
            '"credit_code":"914301005617000000",'
            '"license_no":"SC12443010505553",'
            '"food_categories":["糕点"]}'
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

    import app.tools.food_production_license_ocr_adapter as adapter_module

    monkeypatch.setattr(adapter_module, "OpenAI", StubOpenAI, raising=False)
    adapter = QwenOcrFoodProductionLicenseAdapter(
        model="qwen3.5-ocr",
        base_url="https://example.test/v1",
    )

    result = adapter.extract_text(
        VisionInput(
            content=b"fake-jpg",
            mime_type="image/jpeg",
            file_name="food-production-license.jpg",
        )
    )

    assert result["structured_fields"]["document_type"] == "food_production_license"
    assert result["structured_fields"]["producer_name"] == "长沙波浪食品有限公司"
    assert result["structured_fields"]["license_no"] == "SC12443010505553"
    assert result["metadata"]["provider"] == "qwen_ocr"
    assert result["metadata"]["selected_page"] == 1
    assert calls["model"] == "qwen3.5-ocr"
    prompt = calls["messages"][0]["content"][0]["text"]
    assert "# Skill: food-production-license-review" in prompt
    assert "食品生产许可证" in prompt
    assert "输出要求" not in prompt
    assert "rule_results" not in prompt
