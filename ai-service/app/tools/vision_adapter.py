import os
import base64
import json
from io import BytesIO
from typing import Any, Protocol


class VisionAdapter(Protocol):
    implementation_status: str

    def extract_text(self, source: Any) -> dict[str, Any]:
        ...


class FakeVisionAdapter:
    implementation_status = "fake"

    def __init__(
        self,
        *,
        structured_json_env: str = "BUSINESS_LICENSE_FAKE_VISION_JSON",
        text_env: str = "BUSINESS_LICENSE_FAKE_VISION_TEXT",
        model: str = "fake-business-license-vision",
    ) -> None:
        self.structured_json_env = structured_json_env
        self.text_env = text_env
        self.model = model

    def extract_text(self, source: Any) -> dict[str, Any]:
        structured_json = os.environ.get(self.structured_json_env, "").strip()
        text = os.environ.get(self.text_env, "").strip()
        metadata = {
            "implementation_status": self.implementation_status,
            "provider": "fake",
            "model": self.model,
        }
        if structured_json:
            try:
                return {
                    "text": "",
                    "structured_fields": json.loads(structured_json),
                    "metadata": metadata,
                }
            except json.JSONDecodeError:
                metadata["error_code"] = "VISION_EXTRACTOR_INVALID_JSON"
        if not text:
            metadata["error_code"] = "VISION_EXTRACTOR_NOT_CONFIGURED"
        return {
            "text": text,
            "metadata": metadata,
        }


class VisionInput:
    def __init__(
        self,
        *,
        content: bytes,
        mime_type: str,
        file_name: str | None = None,
        source_url: str | None = None,
        expected_subject_name: str | None = None,
        expected_credit_code: str | None = None,
    ) -> None:
        self.content = content
        self.mime_type = mime_type
        self.file_name = file_name
        self.source_url = source_url
        self.expected_subject_name = expected_subject_name
        self.expected_credit_code = expected_credit_code


def build_business_license_vision_adapter() -> VisionAdapter:
    provider = os.environ.get("BUSINESS_LICENSE_VISION_PROVIDER", "aliyun").strip().lower()
    if provider in {"", "aliyun", "aliyun-ocr", "aliyun_cloud_market_ocr"}:
        from app.tools.aliyun_ocr_adapter import AliyunCloudMarketOcrAdapter

        return AliyunCloudMarketOcrAdapter()
    return FakeVisionAdapter()


def build_food_license_file_adapter() -> VisionAdapter:
    provider = os.environ.get("FOOD_LICENSE_FILE_RECOGNITION_PROVIDER", "fake").strip().lower()
    if provider in {"openai", "langchain-openai"}:
        from app.tools.openai_file_adapter import OpenAiFileAdapter

        return OpenAiFileAdapter(
            provider="openai",
            model=os.environ.get("FOOD_LICENSE_FILE_RECOGNITION_MODEL", "gpt-4o-mini"),
            base_url=os.environ.get("OPENAI_BASE_URL"),
        )
    return FakeVisionAdapter(
        structured_json_env="FOOD_LICENSE_FAKE_LLM_FILE_JSON",
        text_env="FOOD_LICENSE_FAKE_LLM_FILE_TEXT",
        model="fake-food-license-file-recognition",
    )


def _get_value(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def parse_business_license_vision_json(content: str) -> dict[str, Any] | None:
    if not content:
        return None
    candidate = content.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.startswith("json"):
            candidate = candidate[4:].strip()
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        parsed = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def convert_pdf_pages_to_png_data_urls(content: bytes, *, dpi: int = 200) -> list[str]:
    try:
        from pdf2image import convert_from_bytes
    except Exception as error:
        raise RuntimeError("pdf2image is required for scanned PDF recognition") from error

    images = convert_from_bytes(content, dpi=dpi)
    data_urls = []
    for image in images:
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        data_urls.append(f"data:image/png;base64,{encoded}")
    return data_urls


def reject_source_mismatched_fields(
    result: dict[str, Any],
    *,
    expected_subject_name: str | None,
    expected_credit_code: str | None,
) -> dict[str, Any]:
    structured_fields = dict(result.get("structured_fields") or {})
    if not structured_fields:
        return result

    mismatched_fields: dict[str, dict[str, Any]] = {}
    expected_subject = _normalize_compare_text(expected_subject_name)
    actual_subject = _normalize_compare_text(structured_fields.get("subject_name"))
    if expected_subject and actual_subject and actual_subject != expected_subject:
        mismatched_fields["subject_name"] = {
            "expected": expected_subject_name,
            "actual": structured_fields.get("subject_name"),
            "reason": "source_mismatch",
        }

    expected_credit = _normalize_credit_code(expected_credit_code)
    actual_credit = _normalize_credit_code(structured_fields.get("credit_code"))
    if expected_credit and actual_credit and actual_credit != expected_credit:
        mismatched_fields["credit_code"] = {
            "expected": expected_credit_code,
            "actual": structured_fields.get("credit_code"),
            "reason": "source_mismatch",
        }

    if not mismatched_fields:
        return result

    sanitized = {**result, "structured_fields": structured_fields}
    sanitized["metadata"] = {
        **dict(result.get("metadata") or {}),
        "mismatched_fields": mismatched_fields,
        "rejected_fields": mismatched_fields,
    }
    return sanitized


def _normalize_compare_text(value: Any) -> str:
    if value is None:
        return ""
    return "".join(str(value).split()).strip()


def _normalize_credit_code(value: Any) -> str:
    return _normalize_compare_text(value).upper()
