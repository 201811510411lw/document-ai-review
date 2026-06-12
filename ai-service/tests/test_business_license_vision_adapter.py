from app.tools.vision_adapter import (
    FakeVisionAdapter,
    LangChainVisionAdapter,
    _business_license_prompt,
    build_business_license_vision_adapter,
    content_block_for_business_license_file,
    parse_business_license_vision_json,
)


def test_business_license_vision_adapter_defaults_to_fake(monkeypatch):
    monkeypatch.delenv("BUSINESS_LICENSE_VISION_PROVIDER", raising=False)

    adapter = build_business_license_vision_adapter()

    assert isinstance(adapter, FakeVisionAdapter)


def test_business_license_vision_adapter_can_select_langchain_openai(monkeypatch):
    monkeypatch.setenv("BUSINESS_LICENSE_VISION_PROVIDER", "openai")
    monkeypatch.setenv("BUSINESS_LICENSE_VISION_MODEL", "gpt-4o-mini")

    adapter = build_business_license_vision_adapter()

    assert isinstance(adapter, LangChainVisionAdapter)
    assert adapter.implementation_status == "configured"
    assert adapter.provider == "openai"
    assert adapter.model == "gpt-4o-mini"


def test_langchain_vision_adapter_without_api_key_returns_stable_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    adapter = LangChainVisionAdapter(provider="openai", model="gpt-4o-mini")

    result = adapter.extract_text({"content": b"image"})

    assert result["text"] == ""
    assert result["metadata"] == {
        "implementation_status": "not_configured",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "error_code": "VISION_EXTRACTOR_NOT_CONFIGURED",
    }


def test_langchain_vision_adapter_uses_responses_input_file_for_pdf(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = {}

    class StubResponse:
        output_text = '{"document_type":"business_license"}'

    class StubResponses:
        def create(self, **kwargs):
            calls.update(kwargs)
            return StubResponse()

    class StubOpenAI:
        def __init__(self, **kwargs):
            calls["client"] = kwargs
            self.responses = StubResponses()

    import app.tools.vision_adapter as vision_adapter

    monkeypatch.setattr(vision_adapter, "OpenAI", StubOpenAI, raising=False)
    adapter = LangChainVisionAdapter(provider="openai", model="gpt-5.4")

    result = adapter.extract_text(
        {
            "content": b"%PDF-test",
            "mime_type": "application/pdf",
            "file_name": "business-license.pdf",
        }
    )

    assert result["structured_fields"] == {"document_type": "business_license"}
    assert result["metadata"]["api"] == "responses"
    assert calls["client"]["api_key"] == "test-key"
    assert calls["model"] == "gpt-5.4"
    content = calls["input"][0]["content"]
    assert content[0]["type"] == "input_text"
    assert content[1] == {
        "type": "input_file",
        "filename": "business-license.pdf",
        "file_data": "data:application/pdf;base64,JVBERi10ZXN0",
    }


def test_parse_business_license_vision_json_accepts_markdown_json_block():
    parsed = parse_business_license_vision_json(
        """
        ```json
        {
          "document_type": "business_license",
          "subject_name": "成都示例商贸有限公司"
        }
        ```
        """
    )

    assert parsed == {
        "document_type": "business_license",
        "subject_name": "成都示例商贸有限公司",
    }


def test_business_license_prompt_requires_page_selection_and_evidence():
    prompt = _business_license_prompt()

    assert "只从营业执照页面提取字段" in prompt
    assert "忽略身份证" in prompt
    assert "subject_name_evidence" in prompt
    assert "credit_code_evidence" in prompt
    assert "source_page" in prompt
    assert "不要从文件名" in prompt


def test_pdf_content_block_uses_native_file_input():
    block = content_block_for_business_license_file(
        "base64-pdf",
        mime_type="application/pdf",
        file_name="business-license.pdf",
    )

    assert block == {
        "type": "file",
        "file": {
            "filename": "business-license.pdf",
            "file_data": "data:application/pdf;base64,base64-pdf",
        },
    }
