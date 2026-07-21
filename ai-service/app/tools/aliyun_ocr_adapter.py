import base64
import json
import os
import re
from io import BytesIO
from typing import Any

import httpx

from app.tools.vision_adapter import (
    convert_pdf_pages_to_png_data_urls,
    parse_business_license_vision_json,
    reject_source_mismatched_fields,
)

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - dependency absence is handled at runtime.
    OpenAI = None


class AliyunCloudMarketOcrAdapter:
    implementation_status = "configured"

    def __init__(
        self,
        *,
        api_url: str | None = None,
        appcode: str | None = None,
        image_field: str | None = None,
        timeout: float | None = None,
        body_options: dict[str, Any] | None = None,
    ) -> None:
        self.api_url = api_url or os.environ.get("ALIYUN_OCR_API_URL", "")
        self.appcode = appcode or os.environ.get("ALIYUN_OCR_APPCODE", "")
        self.image_field = image_field or os.environ.get("ALIYUN_OCR_IMAGE_FIELD", "img")
        self.timeout = timeout or float(os.environ.get("ALIYUN_OCR_TIMEOUT_SECONDS", "60"))
        self.body_options = body_options or _body_options_from_env()
        self.llm_model = os.environ.get("ALIYUN_OCR_LLM_PARSE_MODEL", "")
        self.llm_base_url = os.environ.get("OPENAI_BASE_URL")
        self.llm_max_attempts = int(os.environ.get("OPENAI_MAX_ATTEMPTS", "3"))
        self.try_rotations = _env_bool("ALIYUN_OCR_TRY_ROTATIONS", default=True)
        self.stop_after_first_license = _env_bool(
            "ALIYUN_OCR_STOP_AFTER_FIRST_LICENSE",
            default=True,
        )
        self.rotation_order = _rotation_order_from_env()
        self.local_prefilter_provider = os.environ.get(
            "ALIYUN_OCR_LOCAL_PREFILTER_PROVIDER",
            "",
        ).strip().lower()

    def extract_text(self, source: Any) -> dict[str, Any]:
        if not self.api_url or not self.appcode:
            return self._error("not_configured", "ALIYUN_OCR_NOT_CONFIGURED")

        content = _get_value(source, "content") or b""
        mime_type = _get_value(source, "mime_type") or "image/png"
        if not content:
            return self._error("failed", "ALIYUN_OCR_EMPTY_CONTENT")

        try:
            pages = _source_pages(content, mime_type)
        except Exception as error:
            return self._error(
                "failed",
                "ALIYUN_OCR_INPUT_CONVERSION_FAILED",
                error_type=type(error).__name__,
                error_message=str(error),
            )

        original_page_count = len(pages)
        pages, local_prefilter_metadata = _prefilter_pdf_pages(
            pages,
            provider=self.local_prefilter_provider,
        )
        page_results: list[dict[str, Any]] = []
        with httpx.Client(timeout=self.timeout) as client:
            for fallback_page_index, page in enumerate(pages, start=1):
                response_result = self._recognize_page_with_orientation(
                    client,
                    page["base64"],
                    try_rotations=self.try_rotations,
                    rotation_order=self.rotation_order,
                )
                response_result["page"] = page.get("page") or fallback_page_index
                page_results.append(response_result)
                if response_result.get("error_code"):
                    break
                if (
                    self.stop_after_first_license
                    and page.get("source") == "pdf"
                    and _is_business_license_complete(response_result.get("text", ""))
                ):
                    break

        error_result = next((item for item in page_results if item.get("error_code")), None)
        if error_result:
            return self._error(
                "failed",
                error_result["error_code"],
                error_type=error_result.get("error_type"),
                error_message=error_result.get("error_message"),
            )

        texts = [item["text"] for item in page_results if item.get("text")]
        document_text = "\n\n".join(texts).strip()
        rule_fields = extract_business_license_fields(document_text)
        llm_result = self._parse_ocr_text_with_llm(document_text)
        llm_metadata = llm_result.get("metadata")
        structured_fields = _merge_rule_and_llm_fields(
            rule_fields,
            llm_result.get("structured_fields") or {},
        )
        selected_page = _selected_business_license_page(page_results)
        if selected_page is not None:
            structured_fields["source_page"] = selected_page

        result = {
            "text": document_text,
            "structured_fields": structured_fields,
            "metadata": {
                "implementation_status": self.implementation_status,
                "provider": "aliyun_cloud_market_ocr",
                "api_url": self.api_url,
                "pages": original_page_count,
                "processed_pages": len(page_results),
                "stopped_after_first_license": (
                    self.stop_after_first_license
                    and len(page_results) < original_page_count
                    and bool(page_results)
                    and _is_business_license_complete(page_results[-1].get("text", ""))
                ),
                "selected_page": selected_page,
                "ignored_pages": _ignored_pages_after_early_stop(
                    page_results,
                    original_page_count,
                    local_prefilter_metadata,
                ),
                "local_prefilter": local_prefilter_metadata or None,
                "structured_extraction": "aliyun_ocr_llm_parse",
                "raw_response_suppressed": True,
            },
        }
        result["metadata"]["llm_parse"] = llm_metadata
        if _debug_enabled():
            result["metadata"]["rule_fields"] = rule_fields
            result["metadata"]["ocr_page_summaries"] = [
                {
                    "page": item.get("page"),
                    "angle": item.get("angle"),
                    "rotation": item.get("rotation"),
                    "word_count": item.get("word_count"),
                    "text": item.get("text"),
                }
                for item in page_results
            ]
        return reject_source_mismatched_fields(
            result,
            expected_subject_name=_get_value(source, "expected_subject_name"),
            expected_credit_code=_get_value(source, "expected_credit_code"),
        )

    def _recognize_page(
        self,
        client: httpx.Client,
        encoded_image: str,
    ) -> dict[str, Any]:
        try:
            response = client.post(
                self.api_url,
                headers={
                    "Authorization": f"APPCODE {self.appcode}",
                    "Content-Type": "application/json; charset=UTF-8",
                },
                json={
                    **self.body_options,
                    self.image_field: encoded_image,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as error:
            return {
                "text": "",
                "error_code": "ALIYUN_OCR_REQUEST_FAILED",
                "error_type": type(error).__name__,
                "error_message": str(error),
            }
        return {
            "text": aliyun_ocr_json_to_text(payload),
            "word_count": payload.get("prism_wnum"),
            "angle": payload.get("angle"),
        }

    def _recognize_page_with_orientation(
        self,
        client: httpx.Client,
        encoded_image: str,
        *,
        try_rotations: bool,
        rotation_order: tuple[int, ...],
    ) -> dict[str, Any]:
        candidates = []
        rotations = rotation_order if try_rotations else (0,)
        for rotation in rotations:
            image = (
                encoded_image
                if rotation == 0
                else _rotate_base64_png(encoded_image, rotation)
            )
            result = self._recognize_page(client, image)
            result["rotation"] = rotation
            candidates.append(result)
            if result.get("error_code"):
                return result
            if _ocr_result_score(result) >= 8:
                break
        return max(candidates, key=_ocr_result_score)

    def _parse_ocr_text_with_llm(self, document_text: str) -> dict[str, Any]:
        if not self.llm_model:
            return {
                "structured_fields": {},
                "metadata": {
                    "implementation_status": "not_configured",
                    "provider": "openai_compatible_chat_completions",
                    "error_code": "ALIYUN_OCR_LLM_PARSE_MODEL_NOT_CONFIGURED",
                },
            }
        if OpenAI is None:
            return {
                "structured_fields": {},
                "metadata": {
                    "implementation_status": "not_configured",
                    "provider": "openai_compatible_chat_completions",
                    "error_code": "ALIYUN_OCR_LLM_PARSE_DEPENDENCY_MISSING",
                },
            }
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return {
                "structured_fields": {},
                "metadata": {
                    "implementation_status": "not_configured",
                    "provider": "openai_compatible_chat_completions",
                    "error_code": "ALIYUN_OCR_LLM_PARSE_NOT_CONFIGURED",
                },
            }
        try:
            client = OpenAI(
                api_key=api_key,
                base_url=self.llm_base_url,
                timeout=self.timeout,
            )
            content, attempts = _create_chat_completion_content(
                client=client,
                model=self.llm_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": ocr_text_parse_prompt(document_text),
                            }
                        ],
                    }
                ],
                max_attempts=self.llm_max_attempts,
            )
        except Exception as error:
            return {
                "structured_fields": {},
                "metadata": {
                    "implementation_status": "failed",
                    "provider": "openai_compatible_chat_completions",
                    "model": self.llm_model,
                    "error_code": "ALIYUN_OCR_LLM_PARSE_FAILED",
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                    "attempts": self.llm_max_attempts,
                },
            }

        structured_fields = parse_business_license_vision_json(content) or {}
        metadata = {
            "implementation_status": "configured",
            "provider": "openai_compatible_chat_completions",
            "model": self.llm_model,
            "api": "chat.completions",
            "attempts": attempts,
        }
        if not structured_fields:
            metadata["error_code"] = "ALIYUN_OCR_LLM_PARSE_JSON_MISSING"
            metadata["raw_response_preview"] = content[:500]
        return {
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
            "provider": "aliyun_cloud_market_ocr",
            "error_code": code,
        }
        if error_type:
            metadata["error_type"] = error_type
        if error_message:
            metadata["error_message"] = error_message
        return {"text": "", "metadata": metadata}


def aliyun_ocr_json_to_text(payload: dict[str, Any]) -> str:
    words = payload.get("prism_wordsInfo") or []
    lines_by_row: dict[Any, list[dict[str, Any]]] = {}
    loose_words: list[str] = []
    for item in words:
        word = str(item.get("word") or "").strip()
        if not word:
            continue
        row_id = item.get("rowId")
        if row_id is None:
            loose_words.append(word)
        else:
            lines_by_row.setdefault(row_id, []).append(item)

    lines = []
    for row_id in sorted(lines_by_row, key=_sort_key):
        row_items = sorted(lines_by_row[row_id], key=lambda item: (item.get("x", 0), item.get("y", 0)))
        line = "".join(str(item.get("word") or "").strip() for item in row_items)
        if line:
            lines.append(line)
    if loose_words:
        lines.append("".join(loose_words))
    return "\n".join(lines).strip()


def extract_business_license_fields(text: str) -> dict[str, Any]:
    normalized_text = _normalize_ocr_text(text)
    fields: dict[str, Any] = {
        "document_type": "business_license" if _is_business_license(normalized_text) else None,
        "subject_name": _extract_labeled_value(
            normalized_text,
            ("名称", "企业名称", "字号名称"),
            stop_labels=("类型", "住所", "经营场所", "法定代表人", "经营者", "注册资本"),
        ),
        "credit_code": _extract_credit_code(normalized_text),
        "business_address": _extract_labeled_value(
            normalized_text,
            ("住所", "经营场所", "营业场所"),
            stop_labels=("法定代表人", "经营者", "注册资本", "成立日期", "营业期限", "经营范围"),
        ),
        "legal_person": _extract_labeled_value(
            normalized_text,
            ("法定代表人", "经营者", "负责人"),
            stop_labels=("注册资本", "成立日期", "营业期限", "经营范围"),
        ),
        "established_date": _extract_date_after_label(normalized_text, ("成立日期", "注册日期")),
        "valid_from": None,
        "valid_to": None,
        "issue_authority": _extract_labeled_value(
            normalized_text,
            ("登记机关", "发照机关"),
            stop_labels=("发照日期", "签发日期", "营业执照"),
        ),
        "issue_date": _extract_date_after_label(normalized_text, ("发照日期", "签发日期", "核准日期")),
        "subject_name_evidence": _extract_evidence(normalized_text, "名称"),
        "credit_code_evidence": _extract_evidence(normalized_text, "统一社会信用代码"),
        "valid_to_evidence": _extract_evidence(normalized_text, "营业期限"),
    }
    valid_from, valid_to = _extract_valid_period(normalized_text)
    fields["valid_from"] = valid_from
    fields["valid_to"] = valid_to
    return fields


def extract_business_license_fields_from_rapidocr(
    content: bytes,
    *,
    rotation: int = 0,
) -> tuple[dict[str, Any], str]:
    """Read visible business-license text locally for missing-field recovery."""
    image_content = _rotate_image_content(content, rotation)
    text = _rapidocr_text(_rapidocr_engine(), image_content)
    return extract_business_license_fields(text), text


def ocr_text_parse_prompt(document_text: str) -> str:
    return (
        "你是营业执照 OCR 文本字段解析器。只允许使用下面 OCR 文本中的内容，"
        "不要使用文件名、上下文、常识或猜测补全。OCR 文本可能顺序错乱、字段标签断裂、"
        "公章遮挡、标点错误。\n"
        "只输出 JSON 对象，不要输出 Markdown。字段包括："
        "document_type, subject_name, credit_code, business_address, legal_person, "
        "established_date, valid_from, valid_to, issue_authority, issue_date, "
        "subject_name_evidence, credit_code_evidence, valid_to_evidence。\n"
        "规则：\n"
        "1. document_type 如果 OCR 文本能确认是营业执照，输出 business_license。\n"
        "2. credit_code 优先提取 18 位统一社会信用代码，必须来自 OCR 原文。\n"
        "3. subject_name 必须是 OCR 原文中公司名称本体，不要把“类型/法定代表人/经营范围”等标签拼进去。\n"
        "4. 如果字段标签被拆散，例如“名\\n类\\n法定代表人经营范围”，请结合附近文本判断，"
        "但没有连续证据时输出 null。\n"
        "5. legal_person 不得输出“经营范围”等字段标签。\n"
        "6. 每个 evidence 字段必须包含 OCR 原文片段；没有原文片段则输出 null。\n"
        "7. 日期尽量规范为 YYYY-MM-DD；无法确定输出 null。\n\n"
        "OCR 文本：\n"
        f"{document_text}"
    )


def _body_options_from_env() -> dict[str, Any]:
    value = os.environ.get("ALIYUN_OCR_BODY_JSON", "").strip()
    if value:
        return json.loads(value)
    return {
        "prob": False,
        "charInfo": False,
        "rotate": True,
        "table": False,
        "sortPage": True,
        "noStamp": False,
        "figure": False,
        "row": True,
        "paragraph": False,
        "oricoord": False,
    }


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


def _rotation_order_from_env() -> tuple[int, ...]:
    value = os.environ.get("ALIYUN_OCR_ROTATION_ORDER", "0,90,180,270")
    rotations: list[int] = []
    for item in value.split(","):
        try:
            rotation = int(item.strip()) % 360
        except ValueError:
            continue
        if rotation in {0, 90, 180, 270} and rotation not in rotations:
            rotations.append(rotation)
    if 0 not in rotations:
        rotations.append(0)
    return tuple(rotations or [0, 90, 180, 270])


def _merge_rule_and_llm_fields(
    rule_fields: dict[str, Any],
    llm_fields: dict[str, Any],
) -> dict[str, Any]:
    merged = {
        **{key: None for key in rule_fields},
        **{key: value for key, value in llm_fields.items() if value is not None},
    }
    if rule_fields.get("credit_code"):
        merged["credit_code"] = rule_fields["credit_code"]
        merged["credit_code_evidence"] = (
            llm_fields.get("credit_code_evidence")
            or rule_fields.get("credit_code_evidence")
        )
    if rule_fields.get("document_type") and not merged.get("document_type"):
        merged["document_type"] = rule_fields["document_type"]
    if llm_fields.get("document_type") == "营业执照":
        merged["document_type"] = "business_license"
    return merged


def _chat_completion_content(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    return str(getattr(message, "content", "") or "").strip()


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


def _source_pages(content: bytes, mime_type: str) -> list[dict[str, str]]:
    if mime_type == "application/pdf":
        return [
            {"base64": data_url.split(",", 1)[1], "source": "pdf", "page": index}
            for index, data_url in enumerate(
                convert_pdf_pages_to_png_data_urls(content, dpi=200),
                start=1,
            )
        ]
    return [
        {
            "base64": base64.b64encode(content).decode("ascii"),
            "source": "image",
            "page": 1,
        }
    ]


def _selected_business_license_page(page_results: list[dict[str, Any]]) -> int | None:
    for item in page_results:
        if _is_business_license(_normalize_ocr_text(item.get("text", ""))):
            return item.get("page")
    return page_results[0].get("page") if page_results else None


def _ignored_pages_after_early_stop(
    page_results: list[dict[str, Any]],
    original_page_count: int,
    local_prefilter_metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    processed_pages = {item.get("page") for item in page_results}
    ignored_pages = [
        {
            "page": page_number,
            "reason": "skipped_by_local_prefilter",
        }
        for page_number in (
            (local_prefilter_metadata or {}).get("ignored_pages") or []
        )
        if page_number not in processed_pages
    ]
    if len(page_results) < original_page_count and page_results:
        last_page = int(page_results[-1].get("page") or len(page_results))
        for page_number in range(last_page + 1, original_page_count + 1):
            if page_number not in processed_pages and all(
                item["page"] != page_number for item in ignored_pages
            ):
                ignored_pages.append(
                    {
                        "page": page_number,
                        "reason": "skipped_after_business_license_page",
                    }
                )
    return ignored_pages


def _prefilter_pdf_pages(
    pages: list[dict[str, Any]],
    *,
    provider: str,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    if provider not in {"rapidocr", "rapid_ocr"}:
        return pages, None
    if not pages or any(page.get("source") != "pdf" for page in pages):
        return pages, None

    try:
        ocr = _rapidocr_engine()
        candidates = []
        for page in pages:
            text = _rapidocr_text(ocr, base64.b64decode(page["base64"]))
            score = _local_prefilter_score(text)
            candidates.append(
                {
                    "page": page.get("page"),
                    "score": score,
                    "text_preview": text[:160],
                }
            )
    except Exception as error:
        return pages, {
            "provider": "rapidocr",
            "status": "failed",
            "error_type": type(error).__name__,
            "error_message": str(error),
        }

    selected = max(candidates, key=lambda item: item["score"], default=None)
    if not selected or selected["score"] < 8:
        return pages, {
            "provider": "rapidocr",
            "status": "no_candidate",
            "candidates": candidates,
        }

    selected_page = selected["page"]
    return [
        page for page in pages if page.get("page") == selected_page
    ], {
        "provider": "rapidocr",
        "status": "selected",
        "selected_page": selected_page,
        "ignored_pages": [
            page.get("page") for page in pages if page.get("page") != selected_page
        ],
        "candidates": candidates,
    }


def _normalize_ocr_text(text: str) -> str:
    return (
        (text or "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("：", ":")
        .replace("　", " ")
        .strip()
    )


def _is_business_license(text: str) -> bool:
    compact = "".join(text.split())
    return "营业执照" in compact or "统一社会信用代码" in compact


def _is_business_license_complete(text: str) -> bool:
    normalized_text = _normalize_ocr_text(text)
    return _is_business_license(normalized_text) and bool(
        _extract_credit_code(normalized_text)
    )


_RAPIDOCR_ENGINE: Any | None = None


def _rapidocr_engine() -> Any:
    global _RAPIDOCR_ENGINE
    if _RAPIDOCR_ENGINE is None:
        from rapidocr import RapidOCR

        _RAPIDOCR_ENGINE = RapidOCR()
    return _RAPIDOCR_ENGINE


def _rapidocr_text(ocr: Any, image_content: bytes) -> str:
    output = ocr(image_content)
    texts = getattr(output, "txts", None)
    if texts is not None:
        return "\n".join(str(text) for text in texts if text)

    fallback_texts = []
    try:
        for item in output:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                fallback_texts.append(str(item[1]))
    except TypeError:
        return ""
    return "\n".join(fallback_texts)


def _local_prefilter_score(text: str) -> int:
    normalized_text = _normalize_ocr_text(text)
    compact = "".join(normalized_text.split())
    score = 0
    if "营业执照" in compact:
        score += 5
    if "统一社会信用代码" in compact or "社会信用代码" in compact:
        score += 4
    if _extract_credit_code(normalized_text):
        score += 3
    if "名称" in compact:
        score += 1
    if "居民身份证" in compact or "公民身份号码" in compact:
        score -= 6
    return score


def _ocr_result_score(result: dict[str, Any]) -> int:
    text = _normalize_ocr_text(result.get("text", ""))
    compact = "".join(text.split())
    score = 0
    if "营业执照" in compact:
        score += 5
    if "统一社会信用代码" in compact:
        score += 4
    if _extract_credit_code(text):
        score += 3
    if "名称" in compact:
        score += 1
    score += min(int(result.get("word_count") or 0), 20) // 5
    if "居民身份证" in compact:
        score -= 4
    return score


def _rotate_base64_png(encoded_image: str, rotation: int) -> str:
    try:
        from PIL import Image
    except Exception as error:
        raise RuntimeError("Pillow is required for OCR rotation fallback") from error

    image = Image.open(BytesIO(base64.b64decode(encoded_image)))
    rotated = image.rotate(rotation, expand=True)
    buffer = BytesIO()
    rotated.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _rotate_image_content(content: bytes, rotation: int) -> bytes:
    if rotation == 0:
        return content
    from PIL import Image, ImageOps

    with Image.open(BytesIO(content)) as image:
        oriented = ImageOps.exif_transpose(image)
        rotated = oriented.rotate(-rotation, expand=True)
        buffer = BytesIO()
        rotated.save(buffer, format="PNG")
    return buffer.getvalue()


def _extract_credit_code(text: str) -> str | None:
    match = re.search(r"(?:统一社会信用代码|信用代码)[:\s]*([0-9A-Z]{15,20})", text, re.I)
    if match:
        return match.group(1).upper()
    match = re.search(r"\b[0-9A-Z]{18}\b", text, re.I)
    return match.group(0).upper() if match else None


def _extract_labeled_value(
    text: str,
    labels: tuple[str, ...],
    *,
    stop_labels: tuple[str, ...],
) -> str | None:
    stop_pattern = "|".join(re.escape(label) for label in stop_labels)
    for label in labels:
        pattern = rf"{re.escape(label)}[:\s]*(.+?)(?=\n|{stop_pattern}[:：]|\Z)"
        match = re.search(pattern, text)
        if match:
            value = _clean_value(match.group(1))
            if value:
                return value
    return None


def _extract_date_after_label(text: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        match = re.search(rf"{re.escape(label)}[:\s]*(\d{{4}}[年./-]\d{{1,2}}[月./-]\d{{1,2}}日?)", text)
        if match:
            return _normalize_date(match.group(1))
    return None


def _extract_valid_period(text: str) -> tuple[str | None, str | None]:
    match = re.search(
        r"营业期限[:\s]*(\d{4}[年./-]\d{1,2}[月./-]\d{1,2}日?)\s*(?:至|-|到)\s*(长期|\d{4}[年./-]\d{1,2}[月./-]\d{1,2}日?)",
        text,
    )
    if not match:
        return None, None
    valid_from = _normalize_date(match.group(1))
    valid_to = "长期" if match.group(2) == "长期" else _normalize_date(match.group(2))
    return valid_from, valid_to


def _extract_evidence(text: str, label: str) -> str | None:
    for line in text.splitlines():
        if label in line:
            return line.strip()[:120]
    return None


def _normalize_date(value: str) -> str:
    match = re.search(r"(\d{4})[年./-](\d{1,2})[月./-](\d{1,2})日?", value)
    if not match:
        return value
    return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def _clean_value(value: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", value).strip(" :：;；")
    return cleaned or None


def _sort_key(value: Any) -> tuple[int, Any]:
    if isinstance(value, int):
        return (0, value)
    return (1, str(value))


def _get_value(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)
