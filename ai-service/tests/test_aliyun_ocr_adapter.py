import base64

from app.tools.aliyun_ocr_adapter import (
    AliyunCloudMarketOcrAdapter,
    _debug_enabled,
    _merge_rule_and_llm_fields,
    _prefilter_pdf_pages,
    _source_pages,
    aliyun_ocr_json_to_text,
    extract_business_license_fields,
)
from app.tools.vision_adapter import build_business_license_vision_adapter


def test_aliyun_ocr_json_to_text_suppresses_layout_details():
    payload = {
        "sid": "sample",
        "angle": 270,
        "prism_wordsInfo": [
            {
                "word": "营业执照",
                "rowId": 1,
                "x": 10,
                "y": 10,
                "pos": [{"x": 1, "y": 2}],
                "charInfo": [{"word": "营", "prob": 99}],
            },
            {"word": "统一社会信用代码:91510100MA0000000X", "rowId": 2, "x": 10, "y": 40},
            {"word": "名称:成都示例商贸有限公司", "rowId": 3, "x": 10, "y": 70},
        ],
    }

    text = aliyun_ocr_json_to_text(payload)

    assert text == (
        "营业执照\n"
        "统一社会信用代码:91510100MA0000000X\n"
        "名称:成都示例商贸有限公司"
    )
    assert "charInfo" not in text
    assert "pos" not in text


def test_extract_business_license_fields_from_aliyun_text():
    text = "\n".join(
        [
            "营业执照",
            "统一社会信用代码:91510100MA0000000X",
            "名称:成都示例商贸有限公司",
            "住所:成都市高新区天府大道 1 号",
            "法定代表人:张三",
            "成立日期:2020年01月02日",
            "营业期限:2020年01月02日至2030年01月01日",
            "登记机关:成都市市场监督管理局",
            "发照日期:2020年01月03日",
        ]
    )

    fields = extract_business_license_fields(text)

    assert fields["document_type"] == "business_license"
    assert fields["subject_name"] == "成都示例商贸有限公司"
    assert fields["credit_code"] == "91510100MA0000000X"
    assert fields["business_address"] == "成都市高新区天府大道 1 号"
    assert fields["legal_person"] == "张三"
    assert fields["established_date"] == "2020-01-02"
    assert fields["valid_from"] == "2020-01-02"
    assert fields["valid_to"] == "2030-01-01"
    assert fields["issue_authority"] == "成都市市场监督管理局"
    assert fields["issue_date"] == "2020-01-03"


def test_business_license_provider_can_build_aliyun_adapter(monkeypatch):
    monkeypatch.setenv("BUSINESS_LICENSE_VISION_PROVIDER", "aliyun")
    monkeypatch.setenv("ALIYUN_OCR_API_URL", "https://example.test/ocr")
    monkeypatch.setenv("ALIYUN_OCR_APPCODE", "appcode")

    adapter = build_business_license_vision_adapter()

    assert adapter.__class__.__name__ == "AliyunCloudMarketOcrAdapter"


def test_aliyun_adapter_selects_rotated_pdf_page_orientation(monkeypatch):
    adapter = AliyunCloudMarketOcrAdapter(api_url="https://example.test", appcode="code")
    calls = []
    responses = [
        {"text": "如0000000管理品识cs出品m1长长", "word_count": 11},
        {"text": "乱码", "word_count": 20},
        {"text": "更多乱码", "word_count": 13},
        {
            "text": (
                "营业执照 统一社会信用代码91510132MA6AULU68M "
                "名称廖记食品有限责任公司"
            ),
            "word_count": 59,
        },
    ]

    def fake_recognize_page(client, encoded_image):
        calls.append(encoded_image)
        return responses[len(calls) - 1]

    monkeypatch.setattr(adapter, "_recognize_page", fake_recognize_page)
    monkeypatch.setattr(
        "app.tools.aliyun_ocr_adapter._rotate_base64_png",
        lambda encoded_image, rotation: f"{encoded_image}-rotated-{rotation}",
    )

    result = adapter._recognize_page_with_orientation(
        object(),
        "page",
        try_rotations=True,
        rotation_order=(0, 90, 180, 270),
    )

    assert result["rotation"] == 270
    assert result["text"].startswith("营业执照")
    assert calls == [
        "page",
        "page-rotated-90",
        "page-rotated-180",
        "page-rotated-270",
    ]


def test_aliyun_adapter_respects_preferred_rotation_order(monkeypatch):
    adapter = AliyunCloudMarketOcrAdapter(api_url="https://example.test", appcode="code")
    calls = []

    def fake_recognize_page(client, encoded_image):
        calls.append(encoded_image)
        return {
            "text": (
                "营业执照 统一社会信用代码91510132MA6AULU68M "
                "名称廖记食品有限责任公司"
            ),
            "word_count": 59,
        }

    monkeypatch.setattr(adapter, "_recognize_page", fake_recognize_page)
    monkeypatch.setattr(
        "app.tools.aliyun_ocr_adapter._rotate_base64_png",
        lambda encoded_image, rotation: f"{encoded_image}-rotated-{rotation}",
    )

    result = adapter._recognize_page_with_orientation(
        object(),
        "page",
        try_rotations=True,
        rotation_order=(270, 0, 90, 180),
    )

    assert result["rotation"] == 270
    assert calls == ["page-rotated-270"]


def test_source_pages_marks_pdf_vs_image(monkeypatch):
    monkeypatch.setattr(
        "app.tools.aliyun_ocr_adapter.convert_pdf_pages_to_png_data_urls",
        lambda content, dpi=200: ["data:image/png;base64,pdf-page"],
    )

    assert _source_pages(b"pdf", "application/pdf") == [
        {"base64": "pdf-page", "source": "pdf", "page": 1}
    ]
    assert _source_pages(b"image", "image/png") == [
        {"base64": "aW1hZ2U=", "source": "image", "page": 1}
    ]


def test_aliyun_local_prefilter_selects_business_license_page(monkeypatch):
    pages = [
        {"base64": base64.b64encode(b"page-1").decode("ascii"), "source": "pdf", "page": 1},
        {"base64": base64.b64encode(b"page-2").decode("ascii"), "source": "pdf", "page": 2},
    ]

    monkeypatch.setattr("app.tools.aliyun_ocr_adapter._rapidocr_engine", lambda: object())
    monkeypatch.setattr(
        "app.tools.aliyun_ocr_adapter._rapidocr_text",
        lambda ocr, content: (
            "营业执照 统一社会信用代码91510132MA6AULU68M 名称廖记食品有限责任公司"
            if content == b"page-1"
            else "中华人民共和国居民身份证 彭德林"
        ),
    )

    selected_pages, metadata = _prefilter_pdf_pages(pages, provider="rapidocr")

    assert selected_pages == [{"base64": base64.b64encode(b"page-1").decode("ascii"), "source": "pdf", "page": 1}]
    assert metadata["status"] == "selected"
    assert metadata["selected_page"] == 1
    assert metadata["ignored_pages"] == [2]


def test_aliyun_local_prefilter_falls_back_when_no_candidate(monkeypatch):
    pages = [
        {"base64": base64.b64encode(b"page-1").decode("ascii"), "source": "pdf", "page": 1},
        {"base64": base64.b64encode(b"page-2").decode("ascii"), "source": "pdf", "page": 2},
    ]

    monkeypatch.setattr("app.tools.aliyun_ocr_adapter._rapidocr_engine", lambda: object())
    monkeypatch.setattr(
        "app.tools.aliyun_ocr_adapter._rapidocr_text",
        lambda ocr, content: "无法判断",
    )

    selected_pages, metadata = _prefilter_pdf_pages(pages, provider="rapidocr")

    assert selected_pages == pages
    assert metadata["status"] == "no_candidate"


def test_aliyun_adapter_stops_after_first_business_license_pdf_page(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    adapter = AliyunCloudMarketOcrAdapter(api_url="https://example.test", appcode="code")
    calls = []

    def fake_source_pages(content, mime_type):
        return [
            {"base64": "page-1", "source": "pdf"},
            {"base64": "page-2", "source": "pdf"},
        ]

    def fake_recognize_page_with_orientation(
        client,
        encoded_image,
        *,
        try_rotations,
        rotation_order,
    ):
        calls.append(encoded_image)
        return {
            "text": (
                "营业执照 统一社会信用代码91510132MA6AULU68M "
                "名称廖记食品有限责任公司"
            ),
            "word_count": 59,
            "rotation": 270,
        }

    monkeypatch.setattr("app.tools.aliyun_ocr_adapter._source_pages", fake_source_pages)
    monkeypatch.setattr(
        adapter,
        "_recognize_page_with_orientation",
        fake_recognize_page_with_orientation,
    )
    monkeypatch.setattr(
        adapter,
        "_parse_ocr_text_with_llm",
        lambda document_text: {
            "structured_fields": {
                "document_type": "business_license",
                "subject_name": "廖记食品有限责任公司",
                "credit_code": "91510132MA6AULU68M",
            },
            "metadata": {"implementation_status": "configured"},
        },
    )

    result = adapter.extract_text({"content": b"pdf", "mime_type": "application/pdf"})

    assert calls == ["page-1"]
    assert result["structured_fields"]["source_page"] == 1
    assert result["metadata"]["pages"] == 2
    assert result["metadata"]["processed_pages"] == 1
    assert result["metadata"]["stopped_after_first_license"] is True
    assert result["metadata"]["ignored_pages"] == [
        {"page": 2, "reason": "skipped_after_business_license_page"}
    ]


def test_aliyun_adapter_parses_ocr_text_with_llm(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = {}

    class StubMessage:
        content = (
            '{"document_type":"business_license",'
            '"subject_name":"廖记食品有限责任公司",'
            '"credit_code":"91510132MA6AULU68M",'
            '"legal_person":"彭德林"}'
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

    import app.tools.aliyun_ocr_adapter as aliyun_ocr_adapter

    monkeypatch.setattr(aliyun_ocr_adapter, "OpenAI", StubOpenAI, raising=False)
    adapter = AliyunCloudMarketOcrAdapter(api_url="https://example.test", appcode="code")
    result = adapter._parse_ocr_text_with_llm(
        "廖记食品有限责任公司其他有限责任公司彭德林\n"
        "-社会信用代码91510132MA6AULU68M"
    )

    assert result["structured_fields"]["subject_name"] == "廖记食品有限责任公司"
    assert result["metadata"]["api"] == "chat.completions"
    assert calls["temperature"] == 0
    assert "OCR 文本" in calls["messages"][0]["content"][0]["text"]


def test_aliyun_adapter_retries_llm_parse_connection_errors(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = {"count": 0}

    class StubMessage:
        content = '{"document_type":"business_license","subject_name":"东鹏饮料"}'

    class StubChoice:
        message = StubMessage()

    class StubResponse:
        choices = [StubChoice()]

    class StubCompletions:
        def create(self, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise ConnectionError("temporary connection error")
            return StubResponse()

    class StubChat:
        completions = StubCompletions()

    class StubOpenAI:
        def __init__(self, **kwargs):
            self.chat = StubChat()

    import app.tools.aliyun_ocr_adapter as aliyun_ocr_adapter

    monkeypatch.setattr(aliyun_ocr_adapter, "OpenAI", StubOpenAI, raising=False)
    adapter = AliyunCloudMarketOcrAdapter(api_url="https://example.test", appcode="code")

    result = adapter._parse_ocr_text_with_llm("营业执照 东鹏饮料")

    assert calls["count"] == 2
    assert result["structured_fields"]["subject_name"] == "东鹏饮料"
    assert result["metadata"]["attempts"] == 2


def test_aliyun_llm_merge_only_uses_rule_fields_for_safe_fallbacks():
    merged = _merge_rule_and_llm_fields(
        {
            "document_type": "business_license",
            "credit_code": "91510132MA6AULU68M",
            "issue_authority": "2024",
            "legal_person": "经营范围",
            "credit_code_evidence": "-社会信用代码91510132MA6AULU68M",
        },
        {
            "document_type": "business_license",
            "subject_name": "廖记食品有限责任公司",
            "legal_person": "彭德林",
            "issue_authority": None,
        },
    )

    assert merged["document_type"] == "business_license"
    assert merged["credit_code"] == "91510132MA6AULU68M"
    assert merged["credit_code_evidence"] == "-社会信用代码91510132MA6AULU68M"
    assert merged["subject_name"] == "廖记食品有限责任公司"
    assert merged["legal_person"] == "彭德林"
    assert merged["issue_authority"] is None


def test_document_ai_review_debug_flag(monkeypatch):
    monkeypatch.setenv("DOCUMENT_AI_REVIEW_DEBUG", "false")
    assert _debug_enabled() is False

    monkeypatch.setenv("DOCUMENT_AI_REVIEW_DEBUG", "true")
    assert _debug_enabled() is True
