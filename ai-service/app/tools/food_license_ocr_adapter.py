import os
import re
import unicodedata
from typing import Any

from app.tools.aliyun_ocr_text_adapter import AliyunOcrTextAdapter
from app.tools.qwen_ocr_adapter import (
    OpenAI,
    _create_chat_completion_content,
    _ocr_response_to_plain_text,
    _source_page_data_urls,
)
from app.tools.skill_rule_review import load_skill_text
from app.tools.vision_adapter import parse_business_license_vision_json


class QwenOcrFoodLicenseAdapter:
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
            or os.environ.get("FOOD_LICENSE_QWEN_OCR_MODEL")
            or os.environ.get("BUSINESS_LICENSE_QWEN_OCR_MODEL", "")
        )
        self.api_key = api_key
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL")
        self.timeout = timeout or float(
            os.environ.get("FOOD_LICENSE_QWEN_OCR_TIMEOUT_SECONDS", "90")
        )
        self.max_attempts = max_attempts or int(
            os.environ.get(
                "FOOD_LICENSE_QWEN_OCR_MAX_ATTEMPTS",
                os.environ.get("OPENAI_MAX_ATTEMPTS", "3"),
            )
        )
        self.max_pages = int(os.environ.get("FOOD_LICENSE_QWEN_OCR_MAX_PAGES", "5"))

    def extract_text(self, source: Any) -> dict[str, Any]:
        if not self.model:
            return self._error("not_configured", "QWEN_OCR_MODEL_NOT_CONFIGURED")
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

        client = OpenAI(api_key=api_key, base_url=self.base_url, timeout=self.timeout)
        page_results: list[dict[str, Any]] = []
        attempts = 0
        try:
            for page_number, data_url in enumerate(page_data_urls[: self.max_pages], start=1):
                content_text, page_attempts = _create_chat_completion_content(
                    client=client,
                    model=self.model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": food_license_qwen_ocr_prompt()},
                                {"type": "image_url", "image_url": {"url": data_url}},
                            ],
                        }
                    ],
                    max_attempts=self.max_attempts,
                )
                attempts += page_attempts
                fields = parse_business_license_vision_json(content_text)
                text = _ocr_response_to_plain_text(content_text)
                page_results.append(
                    {
                        "page": page_number,
                        "raw_text": content_text,
                        "text": text,
                        "fields": _sanitize_food_license_fields(fields or {}),
                        "is_food_license": _is_food_license_page(fields or {}, text),
                    }
                )
                if page_results[-1]["is_food_license"]:
                    break
        except Exception as error:
            return self._error(
                "failed",
                "QWEN_OCR_MODEL_CALL_FAILED",
                error_type=type(error).__name__,
                error_message=str(error),
            )

        selected = _select_food_license_page(page_results)
        metadata = {
            "implementation_status": self.implementation_status,
            "provider": "qwen_ocr",
            "model": self.model,
            "api": "chat.completions",
            "pages": len(page_data_urls),
            "processed_pages": len(page_results),
            "max_pages": self.max_pages,
            "attempts": attempts,
            "structured_extraction": "qwen_food_license_ocr_parse",
            "raw_response_suppressed": True,
            "selected_page": selected.get("page") if selected else None,
            "ignored_pages": [
                {"page": item["page"], "reason": "not_food_license_page"}
                for item in page_results
                if selected is None or item["page"] != selected["page"]
            ],
        }
        if selected is None:
            metadata["error_code"] = "QWEN_OCR_FOOD_LICENSE_PAGE_NOT_FOUND"
            return {
                "text": "\n\n".join(item["text"] for item in page_results).strip(),
                "metadata": metadata,
            }

        structured_fields = _sanitize_food_license_fields(selected["fields"])
        structured_fields["source_page"] = selected["page"]
        return {
            "text": selected["text"],
            "structured_fields": structured_fields,
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


class QwenOcrWithAliyunFallbackFoodLicenseAdapter:
    implementation_status = "configured"

    def __init__(
        self,
        *,
        primary_adapter: Any | None = None,
        fallback_adapter: Any | None = None,
        fallback_text_parser: Any | None = None,
    ) -> None:
        self.primary_adapter = primary_adapter or QwenOcrFoodLicenseAdapter()
        self.fallback_adapter = fallback_adapter or AliyunOcrTextAdapter()
        self.fallback_text_parser = fallback_text_parser or FoodLicenseOcrTextParser()

    def extract_text(self, source: Any) -> dict[str, Any]:
        primary_result = self.primary_adapter.extract_text(source)
        primary_validation = validate_food_license_ocr_result(primary_result)
        if primary_validation["passed"]:
            return _with_fallback_metadata(
                primary_result,
                final_provider="qwen_ocr",
                primary_validation=primary_validation,
                fallback_used=False,
            )

        fallback_ocr_result = self.fallback_adapter.extract_text(source)
        fallback_result = self.fallback_text_parser.extract_text(fallback_ocr_result)
        fallback_validation = validate_food_license_ocr_result(fallback_result)
        return _with_fallback_metadata(
            fallback_result,
            final_provider=str(
                (fallback_result.get("metadata") or {}).get(
                    "provider",
                    "aliyun_ocr_text_llm_parse",
                )
            ),
            primary_validation=primary_validation,
            fallback_validation=fallback_validation,
            fallback_used=True,
            fallback_trigger=primary_validation["failure_reasons"][0],
            primary_result=primary_result,
            fallback_ocr_result=fallback_ocr_result,
        )


class FoodLicenseOcrTextParser:
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
            or os.environ.get("FOOD_LICENSE_TEXT_PARSE_MODEL")
            or os.environ.get("ALIYUN_OCR_LLM_PARSE_MODEL")
            or os.environ.get("BUSINESS_LICENSE_SKILL_REVIEW_MODEL", "")
        )
        self.api_key = api_key
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL")
        self.timeout = timeout or float(
            os.environ.get("FOOD_LICENSE_TEXT_PARSE_TIMEOUT_SECONDS", "90")
        )
        self.max_attempts = max_attempts or int(
            os.environ.get(
                "FOOD_LICENSE_TEXT_PARSE_MAX_ATTEMPTS",
                os.environ.get("OPENAI_MAX_ATTEMPTS", "3"),
            )
        )

    def extract_text(self, ocr_result: dict[str, Any]) -> dict[str, Any]:
        document_text = str(ocr_result.get("text") or "").strip()
        metadata = dict(ocr_result.get("metadata") or {})
        if metadata.get("error_code"):
            return {"text": document_text, "metadata": metadata}
        if not document_text:
            metadata["error_code"] = "ALIYUN_OCR_TEXT_EMPTY"
            return {"text": "", "metadata": metadata}
        if not self.model:
            metadata["error_code"] = "OCR_TEXT_PARSE_MODEL_NOT_CONFIGURED"
            return {"text": document_text, "metadata": metadata}
        if OpenAI is None:
            metadata["error_code"] = "OCR_TEXT_PARSE_DEPENDENCY_MISSING"
            return {"text": document_text, "metadata": metadata}
        api_key = self.api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            metadata["error_code"] = "OCR_TEXT_PARSE_NOT_CONFIGURED"
            return {"text": document_text, "metadata": metadata}

        try:
            client = OpenAI(
                api_key=api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )
            content_text, attempts = _create_chat_completion_content(
                client=client,
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": food_license_ocr_text_parse_prompt(document_text)}
                        ],
                    }
                ],
                max_attempts=self.max_attempts,
            )
        except Exception as error:
            metadata.update(
                {
                    "provider": "aliyun_ocr_text_llm_parse",
                    "error_code": "OCR_TEXT_PARSE_MODEL_CALL_FAILED",
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                }
            )
            return {"text": document_text, "metadata": metadata}

        fields = parse_business_license_vision_json(content_text) or {}
        parsed_metadata = {
            **metadata,
            "provider": "aliyun_ocr_text_llm_parse",
            "model": self.model,
            "api": "chat.completions",
            "attempts": attempts,
            "structured_extraction": "food_license_aliyun_ocr_text_llm_parse",
            "raw_response_suppressed": True,
        }
        if not fields:
            parsed_metadata["error_code"] = "OCR_TEXT_PARSE_JSON_MISSING"
            parsed_metadata["raw_response_preview"] = content_text[:500]
            return {"text": document_text, "metadata": parsed_metadata}
        return {
            "text": document_text,
            "structured_fields": _sanitize_food_license_fields(fields),
            "metadata": parsed_metadata,
        }


def validate_food_license_ocr_result(result: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(result.get("metadata") or {})
    fields = dict(result.get("structured_fields") or {})
    failure_reasons: list[str] = []
    if metadata.get("error_code"):
        failure_reasons.append(str(metadata["error_code"]))

    document_type = str(fields.get("document_type") or "").strip().lower()
    if document_type not in {"food_license", "食品经营许可证"}:
        failure_reasons.append("document_type_invalid")

    if not _normalize_text(fields.get("subject_name")):
        failure_reasons.append("subject_name_missing")

    credit_code = _normalize_credit_code(fields.get("credit_code"))
    if fields.get("credit_code") and len(credit_code) not in {15, 18}:
        failure_reasons.append("credit_code_format_invalid")

    if not _normalize_text(fields.get("license_no")):
        failure_reasons.append("license_no_missing")

    return {
        "passed": not failure_reasons,
        "failure_reasons": failure_reasons,
    }


def food_license_qwen_ocr_prompt() -> str:
    skill_text = _load_skill_extraction_text("food-license-review")
    return (
        "你是证照 OCR 字段抽取器。请严格根据下面 Skill 的字段抽取要求处理当前图片/PDF 页面，"
        "只依据页面可见文字，不要执行合规审核。\n"
        "只输出 JSON 对象，不要输出 Markdown。除 Skill 字段外，可额外输出 source_page、ignored_pages。\n\n"
        "# Skill: food-license-review\n"
        f"{skill_text}"
    )


def food_license_ocr_text_parse_prompt(document_text: str) -> str:
    skill_text = _load_skill_extraction_text("food-license-review")
    return (
        "你是证照 OCR 文本字段解析器。请严格根据下面 Skill 的字段抽取要求解析 OCR 文本，"
        "不要使用文件名、来源系统字段、上下文、常识或猜测补全；不要执行合规审核。\n"
        "只输出 JSON 对象，不要输出 Markdown。\n\n"
        "# Skill: food-license-review\n"
        f"{skill_text}\n\n"
        "OCR 文本：\n"
        f"{document_text}"
    )


def _load_skill_text(skill_name: str) -> str:
    try:
        return load_skill_text(skill_name)
    except Exception:
        return ""


def _load_skill_extraction_text(skill_name: str) -> str:
    skill_text = _load_skill_text(skill_name)
    start = skill_text.find("## 字段抽取要求")
    if start == -1:
        return skill_text
    end = skill_text.find("## 审核规则", start)
    return skill_text[start:end].strip() if end != -1 else skill_text[start:].strip()


def _with_fallback_metadata(
    result: dict[str, Any],
    *,
    final_provider: str,
    primary_validation: dict[str, Any],
    fallback_used: bool,
    fallback_validation: dict[str, Any] | None = None,
    fallback_trigger: str | None = None,
    primary_result: dict[str, Any] | None = None,
    fallback_ocr_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = dict(result.get("metadata") or {})
    metadata["provider"] = "qwen_ocr_with_aliyun_fallback"
    metadata["final_provider"] = final_provider
    metadata["primary_provider"] = "qwen_ocr"
    metadata["fallback_provider"] = "aliyun_ocr_text_llm_parse"
    metadata["fallback_used"] = fallback_used
    metadata["primary_validation"] = primary_validation
    if fallback_validation is not None:
        metadata["fallback_validation"] = fallback_validation
    if fallback_trigger:
        metadata["fallback_trigger"] = fallback_trigger
    if primary_result is not None:
        primary_metadata = dict(primary_result.get("metadata") or {})
        metadata["primary_summary"] = {
            "error_code": primary_metadata.get("error_code"),
            "structured_extraction": primary_metadata.get("structured_extraction"),
            "selected_page": primary_metadata.get("selected_page"),
        }
    if fallback_ocr_result is not None:
        fallback_ocr_metadata = dict(fallback_ocr_result.get("metadata") or {})
        metadata["fallback_ocr_summary"] = {
            "provider": fallback_ocr_metadata.get("provider"),
            "error_code": fallback_ocr_metadata.get("error_code"),
            "processed_pages": fallback_ocr_metadata.get("processed_pages"),
            "selected_page": fallback_ocr_metadata.get("selected_page"),
        }
    return {**result, "metadata": metadata}


def _sanitize_food_license_fields(fields: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(fields)
    for key, value in list(sanitized.items()):
        if isinstance(value, str) and value.strip().lower() in {
            "",
            "null",
            "none",
            "nil",
            "n/a",
            "na",
            "无",
            "空",
        }:
            sanitized[key] = None
    if sanitized.get("document_type") == "食品经营许可证":
        sanitized["document_type"] = "food_license"
    if not isinstance(sanitized.get("business_items"), list):
        value = sanitized.get("business_items")
        sanitized["business_items"] = [value] if value else []
    return sanitized


def _select_food_license_page(page_results: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [item for item in page_results if item.get("is_food_license")]
    if not candidates:
        return None
    return max(candidates, key=lambda item: _food_license_score(item["fields"], item["text"]))


def _is_food_license_page(fields: dict[str, Any], text: str) -> bool:
    compact = "".join((text or "").split())
    document_type = str(fields.get("document_type") or "").lower()
    if document_type in {"food_license", "食品经营许可证"}:
        return True
    if "食品经营许可证" in compact:
        return True
    return bool(fields.get("license_no") and str(fields.get("license_no")).upper().startswith("JY"))


def _food_license_score(fields: dict[str, Any], text: str) -> int:
    compact = "".join((text or "").split())
    score = 0
    if "食品经营许可证" in compact:
        score += 5
    if fields.get("document_type") in {"food_license", "食品经营许可证"}:
        score += 4
    for key in ("subject_name", "credit_code", "license_no", "business_address", "valid_to"):
        if fields.get(key):
            score += 1
    return score


def _normalize_credit_code(value: Any) -> str:
    text = _normalize_text(value).upper()
    return "".join(re.findall(r"[0-9A-Z]", text))


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKC", str(value))
    return "".join(normalized.split()).strip()


def _get_value(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)
