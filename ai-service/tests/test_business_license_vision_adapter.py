from app.tools.vision_adapter import (
    FakeVisionAdapter,
    LangChainVisionAdapter,
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


def test_pdf_content_block_uses_native_file_input():
    block = content_block_for_business_license_file(
        "base64-pdf",
        mime_type="application/pdf",
        file_name="business-license.pdf",
    )

    assert block == {
        "type": "file",
        "source_type": "base64",
        "mime_type": "application/pdf",
        "data": "base64-pdf",
        "filename": "business-license.pdf",
    }
