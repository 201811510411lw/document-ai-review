from app.tools.qwen_ocr_adapter import (
    QwenOcrBusinessLicenseAdapter,
    qwen_ocr_parse_prompt,
)
from app.tools.vision_adapter import VisionInput


def test_qwen_ocr_adapter_requires_model(monkeypatch):
    monkeypatch.delenv("BUSINESS_LICENSE_QWEN_OCR_MODEL", raising=False)

    result = QwenOcrBusinessLicenseAdapter().extract_text(
        {"content": b"fake-png", "mime_type": "image/png"}
    )

    assert result["metadata"]["error_code"] == "QWEN_OCR_MODEL_NOT_CONFIGURED"


def test_qwen_ocr_adapter_calls_openai_compatible_multimodal_api(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = {}

    class StubMessage:
        content = (
            '{"document_type":"business_license",'
            '"subject_name":"成都示例商贸有限公司",'
            '"credit_code":"91510100MA0000000X",'
            '"valid_to":"长期",'
            '"subject_name_evidence":"名称 成都示例商贸有限公司",'
            '"credit_code_evidence":"统一社会信用代码 91510100MA0000000X"}'
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

    import app.tools.qwen_ocr_adapter as qwen_ocr_adapter

    monkeypatch.setattr(qwen_ocr_adapter, "OpenAI", StubOpenAI, raising=False)
    adapter = QwenOcrBusinessLicenseAdapter(model="qwen3.5-ocr", base_url="https://example.test/v1")

    result = adapter.extract_text(
        VisionInput(
            content=b"fake-png",
            mime_type="image/png",
            file_name="business-license.png",
        )
    )

    assert result["structured_fields"]["subject_name"] == "成都示例商贸有限公司"
    assert result["structured_fields"]["credit_code"] == "91510100MA0000000X"
    assert result["metadata"]["provider"] == "qwen_ocr"
    assert result["metadata"]["pages"] == 1
    assert calls["model"] == "qwen3.5-ocr"
    assert calls["temperature"] == 0
    message_content = calls["messages"][0]["content"]
    assert message_content[0]["type"] == "text"
    assert message_content[1]["type"] == "image_url"
    assert message_content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_qwen_ocr_adapter_retries_sideways_image_and_uses_best_rotation(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("BUSINESS_LICENSE_QWEN_OCR_TRY_ROTATIONS", "true")
    responses = [
        (
            '{"document_type":"business_license",'
            '"subject_name":"成都示例商贸有限公司",'
            '"credit_code":"91510100MA0000000X"}'
        ),
        (
            '{"document_type":"business_license",'
            '"subject_name":"成都示例商贸有限公司",'
            '"credit_code":"91510100MA0000000X",'
            '"business_address":"成都市高新区天府大道 1 号",'
            '"legal_person":"张三"}'
        ),
    ]
    calls = []

    class StubMessage:
        def __init__(self, content):
            self.content = content

    class StubChoice:
        def __init__(self, content):
            self.message = StubMessage(content)

    class StubResponse:
        def __init__(self, content):
            self.choices = [StubChoice(content)]

    class StubCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return StubResponse(responses[len(calls) - 1])

    class StubChat:
        completions = StubCompletions()

    class StubOpenAI:
        def __init__(self, **kwargs):
            self.chat = StubChat()

    from io import BytesIO
    from PIL import Image
    import app.tools.qwen_ocr_adapter as qwen_ocr_adapter

    image = Image.new("RGB", (80, 120), "white")
    image_bytes = BytesIO()
    image.save(image_bytes, format="PNG")
    monkeypatch.setattr(qwen_ocr_adapter, "OpenAI", StubOpenAI, raising=False)

    result = QwenOcrBusinessLicenseAdapter(model="qwen3.5-ocr").extract_text(
        VisionInput(content=image_bytes.getvalue(), mime_type="image/png")
    )

    assert len(calls) == 2
    assert result["structured_fields"]["business_address"] == "成都市高新区天府大道 1 号"
    assert result["metadata"]["rotations_attempted"] == [0, 90]
    assert result["metadata"]["selected_rotation"] == 90


def test_qwen_ocr_adapter_recovers_missing_operator_from_local_ocr(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    response_content = (
        '{"document_type":"business_license",'
        '"subject_name":"成都示例商贸有限公司",'
        '"credit_code":"91510100MA0000000X",'
        '"business_address":"成都市高新区天府大道 1 号"}'
    )
    calls = []

    class StubMessage:
        def __init__(self, content):
            self.content = content

    class StubChoice:
        def __init__(self, content):
            self.message = StubMessage(content)

    class StubResponse:
        def __init__(self, content):
            self.choices = [StubChoice(content)]

    class StubCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return StubResponse(response_content)

    class StubChat:
        completions = StubCompletions()

    class StubOpenAI:
        def __init__(self, **kwargs):
            self.chat = StubChat()

    import app.tools.qwen_ocr_adapter as qwen_ocr_adapter

    monkeypatch.setattr(qwen_ocr_adapter, "OpenAI", StubOpenAI, raising=False)
    monkeypatch.setattr(
        qwen_ocr_adapter,
        "extract_business_license_fields_from_rapidocr",
        lambda content, rotation: ({"legal_person": "张三"}, "经营者 张三"),
    )
    result = QwenOcrBusinessLicenseAdapter(model="qwen3.5-ocr").extract_text(
        {"content": b"fake-png", "mime_type": "image/png"}
    )

    assert len(calls) == 1
    assert result["structured_fields"]["legal_person"] == "张三"
    assert result["metadata"]["local_ocr_recovery"]["recovered_fields"] == ["legal_person"]


def test_qwen_ocr_adapter_records_json_missing(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class StubMessage:
        content = "无法识别"

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

    import app.tools.qwen_ocr_adapter as qwen_ocr_adapter

    monkeypatch.setattr(qwen_ocr_adapter, "OpenAI", StubOpenAI, raising=False)
    result = QwenOcrBusinessLicenseAdapter(model="qwen3.5-ocr").extract_text(
        {"content": b"fake-png", "mime_type": "image/png"}
    )

    assert "structured_fields" not in result
    assert result["metadata"]["error_code"] == "QWEN_OCR_STRUCTURED_JSON_MISSING"
    assert result["metadata"]["raw_response_preview"] == "无法识别"


def test_qwen_ocr_adapter_falls_back_to_html_ocr_text(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class StubMessage:
        content = (
            "```html\n"
            "<html><body><h2>营业执照</h2>"
            "<p>统一社会信用代码 91510132MA6AULU68M</p>"
            "<p>名称 廖记食品有限责任公司</p>"
            "<p>住所 成都市温江区成都海峡两岸科技产业开发园蓉台大道南段18号</p>"
            "<p>法人/负责人 彭德林</p>"
            "<p>成立日期 2020年11月11日</p>"
            "</body></html>\n"
            "```"
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

    import app.tools.qwen_ocr_adapter as qwen_ocr_adapter

    monkeypatch.setattr(qwen_ocr_adapter, "OpenAI", StubOpenAI, raising=False)
    result = QwenOcrBusinessLicenseAdapter(model="qwen3.5-ocr").extract_text(
        {"content": b"fake-png", "mime_type": "image/png"}
    )

    fields = result["structured_fields"]
    assert fields["document_type"] == "business_license"
    assert fields["subject_name"] == "廖记食品有限责任公司"
    assert fields["credit_code"] == "91510132MA6AULU68M"
    assert result["metadata"]["structured_extraction"] == "qwen_ocr_text_fallback"


def test_qwen_ocr_adapter_filters_pdf_pages(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("BUSINESS_LICENSE_QWEN_OCR_STOP_AFTER_FIRST_LICENSE", "false")
    calls = {"count": 0}

    responses = [
        (
            "```html\n"
            "<html><body><h2>营业执照</h2>"
            "<p>统一社会信用代码 91510132MA6AULU68M</p>"
            "<p>住所 成都市温江区成都海峡两岸科技产业开发园蓉台大道南段18号</p>"
            "<p>法人/负责人 彭德林</p>"
            "</body></html>\n"
            "```"
        ),
        (
            '{"document_type":"居民身份证",'
            '"subject_name":"彭德林",'
            '"credit_code":"430381198605315058",'
            '"business_address":"null",'
            '"source_page":"null",'
            '"ignored_pages":"null"}'
        ),
    ]

    class StubMessage:
        def __init__(self, content):
            self.content = content

    class StubChoice:
        def __init__(self, content):
            self.message = StubMessage(content)

    class StubResponse:
        def __init__(self, content):
            self.choices = [StubChoice(content)]

    class StubCompletions:
        def create(self, **kwargs):
            index = calls["count"]
            calls["count"] += 1
            return StubResponse(responses[index])

    class StubChat:
        completions = StubCompletions()

    class StubOpenAI:
        def __init__(self, **kwargs):
            self.chat = StubChat()

    import app.tools.qwen_ocr_adapter as qwen_ocr_adapter

    monkeypatch.setattr(qwen_ocr_adapter, "OpenAI", StubOpenAI, raising=False)
    monkeypatch.setattr(
        qwen_ocr_adapter,
        "convert_pdf_pages_to_png_data_urls",
        lambda content, dpi=200: [
            "data:image/png;base64,page-1",
            "data:image/png;base64,page-2",
        ],
    )

    result = QwenOcrBusinessLicenseAdapter(model="qwen3.5-ocr").extract_text(
        {"content": b"fake-pdf", "mime_type": "application/pdf"}
    )

    assert calls["count"] == 2
    assert result["structured_fields"]["document_type"] == "business_license"
    assert result["structured_fields"]["credit_code"] == "91510132MA6AULU68M"
    assert result["structured_fields"]["source_page"] == 1
    assert result["structured_fields"]["ignored_pages"] == [
        {"page": 2, "reason": "identity_card_page"}
    ]
    assert result["metadata"]["selected_page"] == 1
    assert result["metadata"]["structured_extraction"] == "qwen_ocr_page_filter"


def test_qwen_ocr_adapter_stops_after_first_business_license_page(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = {"count": 0}

    class StubMessage:
        content = (
            "```html\n"
            "<html><body><h2>营业执照</h2>"
            "<p>统一社会信用代码 91510132MA6AULU68M</p>"
            "</body></html>\n"
            "```"
        )

    class StubChoice:
        message = StubMessage()

    class StubResponse:
        choices = [StubChoice()]

    class StubCompletions:
        def create(self, **kwargs):
            calls["count"] += 1
            return StubResponse()

    class StubChat:
        completions = StubCompletions()

    class StubOpenAI:
        def __init__(self, **kwargs):
            self.chat = StubChat()

    import app.tools.qwen_ocr_adapter as qwen_ocr_adapter

    monkeypatch.setattr(qwen_ocr_adapter, "OpenAI", StubOpenAI, raising=False)
    monkeypatch.setattr(
        qwen_ocr_adapter,
        "convert_pdf_pages_to_png_data_urls",
        lambda content, dpi=200: [
            "data:image/png;base64,page-1",
            "data:image/png;base64,page-2",
        ],
    )

    result = QwenOcrBusinessLicenseAdapter(model="qwen3.5-ocr").extract_text(
        {"content": b"fake-pdf", "mime_type": "application/pdf"}
    )

    assert calls["count"] == 1
    assert result["structured_fields"]["source_page"] == 1
    assert result["structured_fields"]["ignored_pages"] == [
        {"page": 2, "reason": "skipped_after_business_license_page"}
    ]
    assert result["metadata"]["processed_pages"] == 1
    assert result["metadata"]["stopped_after_first_license"] is True


def test_qwen_ocr_adapter_sanitizes_blank_optional_fields(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class StubMessage:
        content = (
            '{"document_type":"营业执照",'
            '"subject_name":"成都示例商贸有限公司",'
            '"credit_code":"91510100MA0000000X",'
            '"source_page":"",'
            '"ignored_pages":"",'
            '"valid_to":""}'
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

    import app.tools.qwen_ocr_adapter as qwen_ocr_adapter

    monkeypatch.setattr(qwen_ocr_adapter, "OpenAI", StubOpenAI, raising=False)
    result = QwenOcrBusinessLicenseAdapter(model="qwen3.5-ocr").extract_text(
        {"content": b"fake-png", "mime_type": "image/png"}
    )

    fields = result["structured_fields"]
    assert fields["document_type"] == "business_license"
    assert fields["source_page"] is None
    assert fields["ignored_pages"] == []
    assert fields["valid_to"] is None


def test_qwen_ocr_parse_prompt_is_extraction_only():
    prompt = qwen_ocr_parse_prompt()

    assert "只输出 JSON 对象" in prompt
    assert "不要执行合规审核" in prompt
    assert "credit_code" in prompt
