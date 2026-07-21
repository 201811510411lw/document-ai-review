import base64
import os
import re
from io import BytesIO
from typing import Any

from app.tools.aliyun_ocr_adapter import (
    extract_business_license_fields,
    extract_business_license_fields_from_rapidocr,
)
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
        self.model = model or os.environ.get("BUSINESS_LICENSE_QWEN_OCR_MODEL", "")
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
        self.try_rotations = _env_bool(
            "BUSINESS_LICENSE_QWEN_OCR_TRY_ROTATIONS",
            default=True,
        )
        self.rotation_order = _rotation_order_from_env()

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

        return self._extract_image_with_orientation(
            client,
            content=content,
            mime_type=mime_type,
            expected_subject_name=_get_value(source, "expected_subject_name"),
            expected_credit_code=_get_value(source, "expected_credit_code"),
        )

    def _extract_image_with_orientation(
        self,
        client: Any,
        *,
        content: bytes,
        mime_type: str,
        expected_subject_name: str | None,
        expected_credit_code: str | None,
    ) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        try:
            for rotation, data_url in _image_data_url_candidates(
                content,
                mime_type,
                try_rotations=self.try_rotations,
                rotation_order=self.rotation_order,
            ):
                content_text, attempts = self._recognize_page(client, data_url)
                fields, used_text_fallback = _structured_fields_from_ocr_response(
                    content_text
                )
                candidates.append(
                    {
                        "rotation": rotation,
                        "data_url": data_url,
                        "content_text": content_text,
                        "attempts": attempts,
                        "fields": fields,
                        "used_text_fallback": used_text_fallback,
                    }
                )
                if _image_candidate_score(fields) >= 16:
                    break
        except Exception as error:
            return self._error(
                "failed",
                "QWEN_OCR_MODEL_CALL_FAILED",
                error_type=type(error).__name__,
                error_message=str(error),
            )

        selected = max(candidates, key=lambda item: _image_candidate_score(item["fields"]))
        content_text = selected["content_text"]
        structured_fields = selected["fields"]
        metadata = {
            "implementation_status": self.implementation_status,
            "provider": "qwen_ocr",
            "model": self.model,
            "api": "chat.completions",
            "pages": 1,
            "attempts": sum(item["attempts"] for item in candidates),
            "structured_extraction": (
                "qwen_ocr_text_fallback"
                if selected["used_text_fallback"]
                else "qwen_ocr_multimodal_parse"
            ),
            "raw_response_suppressed": True,
            "try_rotations": self.try_rotations,
            "rotation_order": list(self.rotation_order),
            "rotations_attempted": [item["rotation"] for item in candidates],
            "selected_rotation": selected["rotation"],
        }
        if structured_fields:
            recovered_fields, local_ocr_metadata = _recover_missing_fields_with_rapidocr(
                content,
                rotation=selected["rotation"],
                fields=structured_fields,
            )
            if local_ocr_metadata is not None:
                metadata["local_ocr_recovery"] = local_ocr_metadata
            if recovered_fields:
                structured_fields = {**structured_fields, **recovered_fields}
        if not structured_fields:
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
                    expected_subject_name=expected_subject_name,
                    expected_credit_code=expected_credit_code,
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
            expected_subject_name=expected_subject_name,
            expected_credit_code=expected_credit_code,
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

    def _recognize_page(
        self,
        client: Any,
        data_url: str,
    ) -> tuple[str, int]:
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
        "3. subject_name 提取企业/主体名称本体，不要包含字段标签、类型、法定代表人或经营范围。"
        "legal_person 需提取法定代表人、负责人或个体工商户的营业者。\n"
        "4. 日期尽量规范为 YYYY-MM-DD；长期、永久、无固定期限输出 长期；无法确定输出 null。\n"
        "5. subject_name、credit_code 只要输出字段值，就必须同时输出对应 evidence；"
        "evidence 字段必须包含能支撑对应字段的图片/PDF 可见原文片段，不能只重复字段值；没有原文片段输出 null。\n"
        "6. 多页文件只选择营业执照页抽取，source_page 输出页码；ignored_pages 输出被忽略页面及原因。"
    )


def _source_page_data_urls(content: bytes, mime_type: str) -> list[str]:
    if mime_type == "application/pdf":
        return convert_pdf_pages_to_png_data_urls(content, dpi=200)
    encoded_content = base64.b64encode(content).decode("ascii")
    return [f"data:{mime_type};base64,{encoded_content}"]


def _image_data_url_candidates(
    content: bytes,
    mime_type: str,
    *,
    try_rotations: bool,
    rotation_order: tuple[int, ...],
) -> list[tuple[int, str]]:
    original = _source_page_data_urls(content, mime_type)[0]
    rotations = rotation_order if try_rotations else (0,)
    candidates: list[tuple[int, str]] = []
    for rotation in rotations:
        if rotation == 0:
            candidates.append((rotation, original))
            continue
        rotated = _rotated_image_data_url(content, rotation)
        if rotated is not None:
            candidates.append((rotation, rotated))
    return candidates or [(0, original)]


def _rotated_image_data_url(content: bytes, rotation: int) -> str | None:
    try:
        from PIL import Image, ImageOps

        with Image.open(BytesIO(content)) as image:
            oriented = ImageOps.exif_transpose(image)
            rotated = oriented.rotate(-rotation, expand=True)
            buffer = BytesIO()
            rotated.save(buffer, format="PNG")
    except Exception:
        return None
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _structured_fields_from_ocr_response(content_text: str) -> tuple[dict[str, Any], bool]:
    fields = parse_business_license_vision_json(content_text)
    used_text_fallback = fields is None
    if fields is None:
        fields = extract_business_license_fields(_ocr_response_to_plain_text(content_text))
    sanitized = _sanitize_structured_fields(fields or {})
    if sanitized.get("document_type") == "营业执照":
        sanitized["document_type"] = "business_license"
    return (sanitized if _has_key_fields(sanitized) else {}), used_text_fallback


def _recover_missing_fields_with_rapidocr(
    content: bytes,
    *,
    rotation: int,
    fields: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    missing_fields = [
        field
        for field in ("business_address", "legal_person")
        if not fields.get(field)
    ]
    if not missing_fields:
        return {}, None
    try:
        local_fields, _text = extract_business_license_fields_from_rapidocr(
            content,
            rotation=rotation,
        )
    except Exception as error:
        return {}, {
            "provider": "rapidocr",
            "status": "failed",
            "rotation": rotation,
            "error_type": type(error).__name__,
        }
    recovered_fields = {
        field: local_fields[field]
        for field in missing_fields
        if local_fields.get(field)
    }
    return recovered_fields, {
        "provider": "rapidocr",
        "status": "recovered" if recovered_fields else "no_missing_field_found",
        "rotation": rotation,
        "recovered_fields": sorted(recovered_fields),
        "raw_text_suppressed": True,
    }


def _image_candidate_score(fields: dict[str, Any]) -> int:
    score = 0
    if str(fields.get("document_type") or "").strip().lower() == "business_license":
        score += 4
    for field in ("subject_name", "credit_code", "business_address", "legal_person"):
        if fields.get(field):
            score += 3
    for field in ("subject_name_evidence", "credit_code_evidence", "valid_to"):
        if fields.get(field):
            score += 1
    return score


def _rotation_order_from_env() -> tuple[int, ...]:
    raw_value = os.environ.get("BUSINESS_LICENSE_QWEN_OCR_ROTATION_ORDER", "0,90,180,270")
    rotations: list[int] = []
    for value in raw_value.split(","):
        try:
            rotation = int(value.strip()) % 360
        except ValueError:
            continue
        if rotation in {0, 90, 180, 270} and rotation not in rotations:
            rotations.append(rotation)
    return tuple(rotations or [0, 90, 180, 270])


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
