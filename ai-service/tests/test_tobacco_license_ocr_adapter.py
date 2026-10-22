from io import BytesIO

from PIL import Image

from app.tools.tobacco_license_ocr_adapter import QwenOcrTobaccoLicenseAdapter
from app.tools.vision_adapter import VisionInput


def _png_image_bytes() -> bytes:
    image = Image.new("RGB", (80, 120), "white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _install_stub_openai(monkeypatch, responses):
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
            return StubResponse(responses[min(len(calls) - 1, len(responses) - 1)])

    class StubChat:
        completions = StubCompletions()

    class StubOpenAI:
        def __init__(self, **kwargs):
            self.chat = StubChat()

    import app.tools.tobacco_license_ocr_adapter as tobacco_adapter

    monkeypatch.setattr(tobacco_adapter, "OpenAI", StubOpenAI, raising=False)
    return calls


def test_tobacco_adapter_retries_sideways_image_and_uses_best_rotation(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("TOBACCO_LICENSE_QWEN_OCR_TRY_ROTATIONS", "true")
    responses = [
        (
            '{"document_type":"tobacco_license",'
            '"subject_name":"成都示例商贸有限公司"}'
        ),
        (
            '{"document_type":"tobacco_license",'
            '"subject_name":"成都示例商贸有限公司",'
            '"business_address":"成都市高新区天府大道 1 号",'
            '"legal_person":"张三",'
            '"license_no":"510100000001"}'
        ),
    ]
    calls = _install_stub_openai(monkeypatch, responses)

    result = QwenOcrTobaccoLicenseAdapter(model="qwen3.5-ocr").extract_text(
        VisionInput(content=_png_image_bytes(), mime_type="image/png")
    )

    assert len(calls) == 2
    assert result["structured_fields"]["business_address"] == "成都市高新区天府大道 1 号"
    assert result["structured_fields"]["license_no"] == "510100000001"
    assert result["metadata"]["rotations_attempted"] == [0, 90]
    assert result["metadata"]["selected_rotation"] == 90
    assert result["metadata"]["processed_pages"] == 1


def test_tobacco_adapter_skips_rotation_retry_when_disabled(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("TOBACCO_LICENSE_QWEN_OCR_TRY_ROTATIONS", "false")
    responses = [
        (
            '{"document_type":"tobacco_license",'
            '"subject_name":"成都示例商贸有限公司"}'
        ),
    ]
    calls = _install_stub_openai(monkeypatch, responses)

    result = QwenOcrTobaccoLicenseAdapter(model="qwen3.5-ocr").extract_text(
        VisionInput(content=_png_image_bytes(), mime_type="image/png")
    )

    assert len(calls) == 1
    assert result["structured_fields"]["subject_name"] == "成都示例商贸有限公司"
    assert result["metadata"]["rotations_attempted"] == [0]
    assert result["metadata"]["selected_rotation"] == 0
