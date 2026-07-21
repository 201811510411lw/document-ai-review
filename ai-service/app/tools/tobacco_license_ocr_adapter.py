import os
from typing import Any

from app.tools.qwen_ocr_adapter import (
    OpenAI,
    _create_chat_completion_content,
    _ocr_response_to_plain_text,
    _source_page_data_urls,
)
from app.tools.vision_adapter import parse_business_license_vision_json


class QwenOcrTobaccoLicenseAdapter:
    """Extract tobacco-license fields from visible document content only."""

    implementation_status = "configured"

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_attempts: int | None = None,
    ) -> None:
        self.model = (
            model
            or os.environ.get("TOBACCO_LICENSE_QWEN_OCR_MODEL")
            or os.environ.get("BUSINESS_LICENSE_QWEN_OCR_MODEL", "")
        )
        self.api_key = api_key
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL")
        self.timeout = timeout or float(
            os.environ.get("TOBACCO_LICENSE_QWEN_OCR_TIMEOUT_SECONDS", "90")
        )
        self.max_attempts = max_attempts or int(
            os.environ.get(
                "TOBACCO_LICENSE_QWEN_OCR_MAX_ATTEMPTS",
                os.environ.get("OPENAI_MAX_ATTEMPTS", "3"),
            )
        )
        self.max_pages = int(os.environ.get("TOBACCO_LICENSE_QWEN_OCR_MAX_PAGES", "5"))

    def extract_text(self, source: Any) -> dict[str, Any]:
        if not self.model:
            return self._error("not_configured", "QWEN_OCR_MODEL_NOT_CONFIGURED")
        if OpenAI is None:
            return self._error("not_configured", "QWEN_OCR_DEPENDENCY_MISSING")

        api_key = self.api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return self._error("not_configured", "QWEN_OCR_NOT_CONFIGURED")

        content = _value(source, "content") or b""
        mime_type = _value(source, "mime_type") or "image/png"
        if not content:
            return self._error("failed", "QWEN_OCR_EMPTY_CONTENT")

        try:
            page_data_urls = _source_page_data_urls(content, mime_type)
        except Exception as error:
            return self._error(
                "failed",
                "QWEN_OCR_INPUT_CONVERSION_FAILED",
                error_type=type(error).__name__,
                error_message=str(error),
            )

        client = OpenAI(api_key=api_key, base_url=self.base_url, timeout=self.timeout)
        pages: list[dict[str, Any]] = []
        attempts = 0
        try:
            for page_number, data_url in enumerate(page_data_urls[: self.max_pages], start=1):
                response, page_attempts = _create_chat_completion_content(
                    client=client,
                    model=self.model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": tobacco_license_qwen_ocr_prompt()},
                                {"type": "image_url", "image_url": {"url": data_url}},
                            ],
                        }
                    ],
                    max_attempts=self.max_attempts,
                )
                attempts += page_attempts
                fields = _sanitize_fields(parse_business_license_vision_json(response) or {})
                text = _ocr_response_to_plain_text(response)
                pages.append(
                    {
                        "page": page_number,
                        "text": text,
                        "fields": fields,
                        "is_tobacco_license": _is_tobacco_license(fields, text),
                    }
                )
                if pages[-1]["is_tobacco_license"]:
                    break
        except Exception as error:
            return self._error(
                "failed",
                "QWEN_OCR_MODEL_CALL_FAILED",
                error_type=type(error).__name__,
                error_message=str(error),
            )

        selected = next((page for page in pages if page["is_tobacco_license"]), None)
        metadata = {
            "implementation_status": self.implementation_status,
            "provider": "qwen_ocr",
            "model": self.model,
            "pages": len(page_data_urls),
            "processed_pages": len(pages),
            "attempts": attempts,
            "structured_extraction": "qwen_tobacco_license_ocr_parse",
            "selected_page": selected["page"] if selected else None,
        }
        if selected is None:
            return {
                "text": "\n\n".join(page["text"] for page in pages).strip(),
                "metadata": {**metadata, "error_code": "QWEN_OCR_TOBACCO_LICENSE_PAGE_NOT_FOUND"},
            }

        return {
            "text": selected["text"],
            "structured_fields": {**selected["fields"], "source_page": selected["page"]},
            "metadata": metadata,
        }

    def _error(
        self,
        status: str,
        code: str,
        *,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        metadata = {
            "implementation_status": status,
            "provider": "qwen_ocr",
            "model": self.model,
            "error_code": code,
        }
        if error_type:
            metadata["error_type"] = error_type
        if error_message:
            metadata["error_message"] = error_message
        return {"text": "", "metadata": metadata}


def tobacco_license_qwen_ocr_prompt() -> str:
    return (
        "你是烟草专卖零售许可证 OCR 字段抽取器。只允许依据图片/PDF 页面中的可见文字，"
        "不得使用文件名、OA 申请信息、门店名称或常识猜测。只输出 JSON 对象，不要 Markdown。"
        "字段：document_type, subject_name, business_address, legal_person, license_no, valid_from, valid_to。"
        "document_type 仅在可确认大标题为烟草专卖零售许可证时输出 tobacco_license，否则输出 null。"
        "subject_name 提取许可证上的企业/经营主体；business_address 提取经营场所；"
        "legal_person 提取负责人、经营者或法定代表人；license_no 提取许可证号。"
        "日期规范为 YYYY-MM-DD，长期有效输出 长期，无法确认输出 null。"
    )


def _value(source: Any, key: str) -> Any:
    return source.get(key) if isinstance(source, dict) else getattr(source, key, None)


def _sanitize_fields(fields: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(fields)
    for key, value in list(sanitized.items()):
        if isinstance(value, str) and value.strip() in {"", "-", "null", "None", "未知"}:
            sanitized[key] = None
    if sanitized.get("document_type") in {"烟草专卖零售许可证", "烟草证"}:
        sanitized["document_type"] = "tobacco_license"
    return sanitized


def _is_tobacco_license(fields: dict[str, Any], text: str) -> bool:
    return fields.get("document_type") == "tobacco_license" or "烟草专卖零售许可证" in text
