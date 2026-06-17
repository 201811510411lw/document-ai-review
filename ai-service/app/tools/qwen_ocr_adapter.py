import base64
import os
import re
from typing import Any

from app.tools.aliyun_ocr_adapter import extract_business_license_fields
from app.tools.vision_adapter import (
    convert_pdf_pages_to_png_data_urls,
    parse_business_license_vision_json,
    reject_source_mismatched_fields,
)

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - dependency absence is handled at runtime.
    OpenAI = None


class QwenOcrBusinessLicenseAdapter:
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
        self.model = model or os.environ.get(
            "BUSINESS_LICENSE_QWEN_OCR_MODEL",
            os.environ.get("BUSINESS_LICENSE_VISION_MODEL", "qwen3.5-ocr"),
        )
        self.api_key = api_key
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL")
        self.timeout = timeout or float(
            os.environ.get("BUSINESS_LICENSE_QWEN_OCR_TIMEOUT_SECONDS", "90")
        )
        self.max_attempts = max_attempts or int(
            os.environ.get(
                "BUSINESS_LICENSE_QWEN_OCR_MAX_ATTEMPTS",
                os.environ.get("OPENAI_MAX_ATTEMPTS", "3"),
            )
        )
        self.max_pages = int(os.environ.get("BUSINESS_LICENSE_QWEN_OCR_MAX_PAGES", "5"))
        self.stop_after_first_license = _env_bool(
            "BUSINESS_LICENSE_QWEN_OCR_STOP_AFTER_FIRST_LICENSE",
            default=True,
        )

    def extract_text(self, source: Any) -> dict[str, Any]:
        if OpenAI is None:
            return self._error("not_configured", "QWEN_OCR_DEPENDENCY_MISSING")

        api_key = self.api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return self._error("not_configured", "QWEN_OCR_NOT_CONFIGURED")

        content = _get_value(source, "content") or b""
        mime_type = _get_value(source, "mime_type") or "image/png"
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

        client = OpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )
        if len(page_data_urls) > 1:
            return self._extract_pdf_pages(
                client,
                page_data_urls[: self.max_pages],
                original_page_count=len(page_data_urls),
                expected_subject_name=_get_value(source, "expected_subject_name"),
                expected_credit_code=_get_value(source, "expected_credit_code"),
            )

        try:
            content_text, attempts = self._recognize_page(client, page_data_urls[0])
        except Exception as error:
            return self._error(
                "failed",
                "QWEN_OCR_MODEL_CALL_FAILED",
                error_type=type(error).__name__,
                error_message=str(error),
            )

        structured_fields = parse_business_license_vision_json(content_text)
        metadata = {
            "implementation_status": self.implementation_status,
            "provider": "qwen_ocr",
            "model": self.model,
            "api": "chat.completions",
            "pages": len(page_data_urls),
            "attempts": attempts,
            "structured_extraction": "qwen_ocr_multimodal_parse",
            "raw_response_suppressed": True,
        }
        if structured_fields is None:
            fallback_text = _ocr_response_to_plain_text(content_text)
            structured_fields = _sanitize_structured_fields(
                extract_business_license_fields(fallback_text)
            )
            if _has_key_fields(structured_fields):
                metadata["structured_extraction"] = "qwen_ocr_text_fallback"
                result = {
                    "text": fallback_text,
                    "structured_fields": structured_fields,
                    "metadata": metadata,
                }
                return reject_source_mismatched_fields(
                    result,
                    expected_subject_name=_get_value(source, "expected_subject_name"),
                    expected_credit_code=_get_value(source, "expected_credit_code"),
                )
            metadata["error_code"] = "QWEN_OCR_STRUCTURED_JSON_MISSING"
            metadata["raw_response_preview"] = content_text[:500]
            result = {"text": content_text, "metadata": metadata}
        else:
            structured_fields = _sanitize_structured_fields(structured_fields)
            if structured_fields.get("document_type") == "营业执照":
                structured_fields["document_type"] = "business_license"
            result = {
                "text": content_text,
                "structured_fields": structured_fields,
                "metadata": metadata,
            }
        return reject_source_mismatched_fields(
            result,
            expected_subject_name=_get_value(source, "expected_subject_name"),
            expected_credit_code=_get_value(source, "expected_credit_code"),
        )

    def _extract_pdf_pages(
        self,
        client: Any,
        page_data_urls: list[str],
        *,
        original_page_count: int,
        expected_subject_name: str | None,
        expected_credit_code: str | None,
    ) -> dict[str, Any]:
        page_results: list[dict[str, Any]] = []
        total_attempts = 0
        try:
            for page_number, data_url in enumerate(page_data_urls, start=1):
                content_text, attempts = self._recognize_page(client, data_url)
                total_attempts += attempts
                plain_text = _ocr_response_to_plain_text(content_text)
                parsed_fields = parse_business_license_vision_json(content_text)
                if parsed_fields is None:
                    parsed_fields = extract_business_license_fields(plain_text)
                parsed_fields = _sanitize_structured_fields(parsed_fields or {})
                if _is_business_license_page(parsed_fields, plain_text):
                    parsed_fields["document_type"] = "business_license"
                page_results.append(
                    {
                        "page": page_number,
                        "raw_text": content_text,
                        "text": plain_text,
                        "fields": parsed_fields,
                        "is_business_license": _is_business_license_page(
                            parsed_fields,
                            plain_text,
                        ),
                        "reason": _page_reason(parsed_fields, plain_text),
                    }
                )
                if (
                    self.stop_after_first_license
                    and page_results[-1]["is_business_license"]
                ):
                    break
        except Exception as error:
            return self._error(
                "failed",
                "QWEN_OCR_MODEL_CALL_FAILED",
                error_type=type(error).__name__,
                error_message=str(error),
            )

        selected = _select_business_license_page(page_results)
        metadata = {
            "implementation_status": self.implementation_status,
            "provider": "qwen_ocr",
            "model": self.model,
            "api": "chat.completions",
            "pages": original_page_count,
            "processed_pages": len(page_results),
            "max_pages": self.max_pages,
            "stopped_after_first_license": (
                self.stop_after_first_license
                and bool(page_results)
                and bool(page_results[-1].get("is_business_license"))
                and len(page_results) < min(original_page_count, self.max_pages)
            ),
            "attempts": total_attempts,
            "structured_extraction": "qwen_ocr_page_filter",
            "raw_response_suppressed": True,
            "selected_page": selected.get("page") if selected else None,
            "ignored_pages": [
                {"page": item["page"], "reason": item["reason"]}
                for item in page_results
                if selected is None or item["page"] != selected["page"]
            ],
        }
        processed_count = len(page_results)
        for page_number in range(processed_count + 1, min(original_page_count, self.max_pages) + 1):
            metadata["ignored_pages"].append(
                {"page": page_number, "reason": "skipped_after_business_license_page"}
            )
        for page_number in range(self.max_pages + 1, original_page_count + 1):
            metadata["ignored_pages"].append(
                {"page": page_number, "reason": "skipped_by_max_pages"}
            )
        if _debug_enabled():
            metadata["page_summaries"] = [
                {
                    "page": item["page"],
                    "is_business_license": item["is_business_license"],
                    "reason": item["reason"],
                    "fields": {
                        key: item["fields"].get(key)
                        for key in ("document_type", "subject_name", "credit_code")
                    },
                    "text_preview": item["text"][:500],
                }
                for item in page_results
            ]
        if selected is None:
            metadata["error_code"] = "QWEN_OCR_BUSINESS_LICENSE_PAGE_NOT_FOUND"
            return {
                "text": "\n\n".join(item["text"] for item in page_results).strip(),
                "metadata": metadata,
            }

        structured_fields = _sanitize_structured_fields(selected["fields"])
        structured_fields["source_page"] = selected["page"]
        structured_fields["ignored_pages"] = metadata["ignored_pages"]
        result = {
            "text": selected["text"],
            "structured_fields": structured_fields,
            "metadata": metadata,
        }
        return reject_source_mismatched_fields(
            result,
            expected_subject_name=expected_subject_name,
            expected_credit_code=expected_credit_code,
        )

    def _recognize_page(self, client: Any, data_url: str) -> tuple[str, int]:
        return _create_chat_completion_content(
            client=client,
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": qwen_ocr_parse_prompt()},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                }
            ],
            max_attempts=self.max_attempts,
        )

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


def qwen_ocr_parse_prompt() -> str:
    return (
        "你是营业执照 OCR 字段抽取器。只允许依据图片/PDF 页面中的可见文字抽取字段，"
        "不要使用文件名、上下文、常识或猜测补全；不要执行合规审核。\n"
        "只输出 JSON 对象，不要输出 Markdown。字段包括："
        "document_type, subject_name, credit_code, business_address, legal_person, "
        "established_date, valid_from, valid_to, issue_authority, issue_date, "
        "source_page, ignored_pages, subject_name_evidence, credit_code_evidence, valid_to_evidence。\n"
        "规则：\n"
        "1. document_type 如果能确认是营业执照，输出 business_license；否则输出 null。\n"
        "2. credit_code 提取统一社会信用代码，必须来自证照原文。\n"
        "3. subject_name 提取企业/主体名称本体，不要包含字段标签、类型、法定代表人或经营范围。\n"
        "4. 日期尽量规范为 YYYY-MM-DD；长期、永久、无固定期限输出 长期；无法确定输出 null。\n"
        "5. evidence 字段必须包含能支撑对应字段的原文片段；没有原文片段输出 null。\n"
        "6. 多页文件只选择营业执照页抽取，source_page 输出页码；ignored_pages 输出被忽略页面及原因。"
    )


def _source_page_data_urls(content: bytes, mime_type: str) -> list[str]:
    if mime_type == "application/pdf":
        return convert_pdf_pages_to_png_data_urls(content, dpi=200)
    encoded_content = base64.b64encode(content).decode("ascii")
    return [f"data:{mime_type};base64,{encoded_content}"]


def _create_chat_completion_content(
    *,
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    max_attempts: int,
) -> tuple[str, int]:
    attempts = max(1, max_attempts)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
            )
            return _chat_completion_content(response), attempt
        except Exception as error:
            last_error = error
    if last_error is not None:
        raise last_error
    return "", attempts


def _chat_completion_content(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    return str(getattr(message, "content", "") or "").strip()


def _sanitize_structured_fields(fields: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(fields)
    for key, value in list(sanitized.items()):
        if isinstance(value, str) and _is_blank_placeholder(value):
            sanitized[key] = None
    sanitized["ignored_pages"] = (
        sanitized["ignored_pages"] if isinstance(sanitized.get("ignored_pages"), list) else []
    )
    source_page = sanitized.get("source_page")
    if isinstance(source_page, int):
        return sanitized
    if isinstance(source_page, str) and source_page.strip().isdigit():
        sanitized["source_page"] = int(source_page.strip())
    else:
        sanitized["source_page"] = None
    return sanitized


def _has_key_fields(fields: dict[str, Any]) -> bool:
    return bool(fields.get("document_type") or fields.get("subject_name") or fields.get("credit_code"))


def _select_business_license_page(page_results: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [item for item in page_results if item.get("is_business_license")]
    if not candidates:
        return None
    return max(candidates, key=lambda item: _business_license_score(item["fields"], item["text"]))


def _is_business_license_page(fields: dict[str, Any], text: str) -> bool:
    compact = "".join((text or "").split())
    document_type = str(fields.get("document_type") or "").lower()
    if document_type in {"居民身份证", "identity_card", "id_card"}:
        return False
    if "居民身份证" in compact or "公民身份号码" in compact:
        return False
    if document_type in {"business_license", "营业执照"}:
        return True
    if "营业执照" in compact or "统一社会信用代码" in compact:
        return True
    return bool(fields.get("credit_code") and fields.get("business_address"))


def _business_license_score(fields: dict[str, Any], text: str) -> int:
    compact = "".join((text or "").split())
    score = 0
    if "营业执照" in compact:
        score += 5
    if "统一社会信用代码" in compact:
        score += 4
    if fields.get("document_type") in {"business_license", "营业执照"}:
        score += 4
    for key in ("subject_name", "credit_code", "business_address", "legal_person", "established_date"):
        if fields.get(key):
            score += 1
    if "居民身份证" in compact:
        score -= 6
    return score


def _page_reason(fields: dict[str, Any], text: str) -> str:
    compact = "".join((text or "").split())
    document_type = str(fields.get("document_type") or "")
    if document_type in {"居民身份证", "identity_card", "id_card"}:
        return "identity_card_page"
    if "居民身份证" in compact or "身份证" in compact:
        return "identity_card_page"
    if _is_business_license_page(fields, text):
        return "business_license_candidate"
    return "not_business_license_page"


def _is_blank_placeholder(value: str) -> bool:
    return value.strip().lower() in {"", "null", "none", "nil", "n/a", "na", "无", "空"}


def _ocr_response_to_plain_text(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("html"):
            text = text[4:].strip()
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", text)
    text = re.sub(r"(?i)</\s*(p|h[1-6]|div|li|tr)\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _debug_enabled() -> bool:
    return os.environ.get("DOCUMENT_AI_REVIEW_DEBUG", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_value(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)
