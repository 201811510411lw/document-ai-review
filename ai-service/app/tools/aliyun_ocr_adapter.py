import base64
import json
import os
import re
from typing import Any

import httpx

from app.tools.vision_adapter import (
    VisionInput,
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
        self.llm_model = os.environ.get(
            "ALIYUN_OCR_LLM_PARSE_MODEL",
            os.environ.get("BUSINESS_LICENSE_VISION_MODEL", "gpt-4o-mini"),
        )
        self.llm_base_url = os.environ.get("OPENAI_BASE_URL")

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

        page_results: list[dict[str, Any]] = []
        with httpx.Client(timeout=self.timeout) as client:
            for page_index, page in enumerate(pages, start=1):
                response_result = self._recognize_page(client, page["base64"])
                response_result["page"] = page_index
                page_results.append(response_result)
                if response_result.get("error_code"):
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
                "pages": len(page_results),
                "selected_page": selected_page,
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

    def _parse_ocr_text_with_llm(self, document_text: str) -> dict[str, Any]:
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
            response = client.chat.completions.create(
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
                temperature=0,
            )
            content = _chat_completion_content(response)
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
                },
            }

        structured_fields = parse_business_license_vision_json(content) or {}
        metadata = {
            "implementation_status": "configured",
            "provider": "openai_compatible_chat_completions",
            "model": self.llm_model,
            "api": "chat.completions",
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


def _source_pages(content: bytes, mime_type: str) -> list[dict[str, str]]:
    if mime_type == "application/pdf":
        return [
            {"base64": data_url.split(",", 1)[1]}
            for data_url in convert_pdf_pages_to_png_data_urls(content, dpi=200)
        ]
    return [{"base64": base64.b64encode(content).decode("ascii")}]


def _selected_business_license_page(page_results: list[dict[str, Any]]) -> int | None:
    for item in page_results:
        if _is_business_license(_normalize_ocr_text(item.get("text", ""))):
            return item.get("page")
    return page_results[0].get("page") if page_results else None


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
