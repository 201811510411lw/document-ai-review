import os
import base64
import json
from typing import Any, Protocol

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - dependency absence is handled at runtime.
    OpenAI = None


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


class LangChainVisionAdapter:
    implementation_status = "configured"

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int = 60,
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout

    def extract_text(self, source: Any) -> dict[str, Any]:
        api_key = self.api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return self._error("not_configured", "VISION_EXTRACTOR_NOT_CONFIGURED")
        try:
            from langchain_core.messages import HumanMessage
            from langchain_openai import ChatOpenAI
        except Exception:
            return self._error("not_configured", "VISION_EXTRACTOR_DEPENDENCY_MISSING")

        content = _get_value(source, "content") or b""
        mime_type = _get_value(source, "mime_type") or "image/png"
        if not content:
            return self._error("failed", "VISION_EXTRACTOR_EMPTY_CONTENT")

        encoded_content = base64.b64encode(content).decode("ascii")
        if mime_type == "application/pdf":
            return self._extract_pdf_with_responses_api(
                encoded_content,
                api_key=api_key,
                file_name=_get_value(source, "file_name"),
            )

        model = ChatOpenAI(
            model=self.model,
            api_key=api_key,
            base_url=self.base_url or os.environ.get("OPENAI_BASE_URL"),
            timeout=self.timeout,
        )
        try:
            response = model.invoke(
                [
                    HumanMessage(
                        content=[
                            {
                                "type": "text",
                                "text": _business_license_prompt(),
                            },
                            content_block_for_business_license_file(
                                encoded_content,
                                mime_type=mime_type,
                                file_name=_get_value(source, "file_name"),
                            ),
                        ]
                    )
                ]
            )
        except Exception as error:
            return self._error(
                "failed",
                "VISION_EXTRACTOR_MODEL_CALL_FAILED",
                error_type=type(error).__name__,
                error_message=str(error),
            )
        content = str(getattr(response, "content", "") or "").strip()
        structured_fields = parse_business_license_vision_json(content)
        metadata = {
            "implementation_status": self.implementation_status,
            "provider": self.provider,
            "model": self.model,
        }
        if structured_fields is None:
            metadata["error_code"] = "VISION_EXTRACTOR_STRUCTURED_JSON_MISSING"
            metadata["raw_response_preview"] = content[:500]
        result = {"text": content, "metadata": metadata}
        if structured_fields is not None:
            result["structured_fields"] = structured_fields
        return result

    def _extract_pdf_with_responses_api(
        self,
        encoded_content: str,
        *,
        api_key: str,
        file_name: str | None,
    ) -> dict[str, Any]:
        if OpenAI is None:
            return self._error("not_configured", "VISION_EXTRACTOR_DEPENDENCY_MISSING")

        client = OpenAI(
            api_key=api_key,
            base_url=self.base_url or os.environ.get("OPENAI_BASE_URL"),
            timeout=self.timeout,
        )
        try:
            response = client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": _business_license_prompt()},
                            {
                                "type": "input_file",
                                "filename": file_name or "document.pdf",
                                "file_data": (
                                    "data:application/pdf;base64,"
                                    f"{encoded_content}"
                                ),
                            },
                        ],
                    }
                ],
            )
        except Exception as error:
            return self._error(
                "failed",
                "VISION_EXTRACTOR_MODEL_CALL_FAILED",
                error_type=type(error).__name__,
                error_message=str(error),
            )

        content = str(getattr(response, "output_text", "") or "").strip()
        structured_fields = parse_business_license_vision_json(content)
        metadata = {
            "implementation_status": self.implementation_status,
            "provider": self.provider,
            "model": self.model,
            "api": "responses",
        }
        if structured_fields is None:
            metadata["error_code"] = "VISION_EXTRACTOR_STRUCTURED_JSON_MISSING"
            metadata["raw_response_preview"] = content[:500]
        result = {"text": content, "metadata": metadata}
        if structured_fields is not None:
            result["structured_fields"] = structured_fields
        return result

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
            "provider": self.provider,
            "model": self.model,
            "error_code": code,
        }
        if error_type:
            metadata["error_type"] = error_type
        if error_message:
            metadata["error_message"] = error_message
        return {
            "text": "",
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
    ) -> None:
        self.content = content
        self.mime_type = mime_type
        self.file_name = file_name
        self.source_url = source_url


def build_business_license_vision_adapter() -> VisionAdapter:
    provider = os.environ.get("BUSINESS_LICENSE_VISION_PROVIDER", "fake").strip().lower()
    if provider in {"openai", "langchain-openai"}:
        return LangChainVisionAdapter(
            provider="openai",
            model=os.environ.get("BUSINESS_LICENSE_VISION_MODEL", "gpt-4o-mini"),
            base_url=os.environ.get("OPENAI_BASE_URL"),
        )
    return FakeVisionAdapter()


def build_food_license_file_adapter() -> VisionAdapter:
    provider = os.environ.get("FOOD_LICENSE_FILE_RECOGNITION_PROVIDER", "fake").strip().lower()
    if provider in {"openai", "langchain-openai"}:
        return LangChainVisionAdapter(
            provider="openai",
            model=os.environ.get("FOOD_LICENSE_FILE_RECOGNITION_MODEL", "gpt-4o-mini"),
            base_url=os.environ.get("OPENAI_BASE_URL"),
        )
    return FakeVisionAdapter(
        structured_json_env="FOOD_LICENSE_FAKE_LLM_FILE_JSON",
        text_env="FOOD_LICENSE_FAKE_LLM_FILE_TEXT",
        model="fake-food-license-file-recognition",
    )


def _business_license_prompt() -> str:
    return (
        "请从输入的营业执照图片或PDF中提取字段，只输出JSON对象，不要输出Markdown。"
        "输入可能是多页文件，可能混有身份证或其他材料。请先逐页判断文档类型，"
        "只从营业执照页面提取字段，忽略身份证、空白页、扫描软件水印和其他无关页面。"
        "字段包括 document_type, subject_name, credit_code, business_address, "
        "legal_person, established_date, valid_from, valid_to, issue_authority, issue_date, "
        "source_page, ignored_pages, subject_name_evidence, credit_code_evidence, valid_to_evidence。"
        "subject_name 必须来自营业执照上“名称”字段后面的可见文字，"
        "不要从文件名、印章、二维码、上下文、常识或其他页面推断。"
        "credit_code 必须来自“统一社会信用代码”字段后的可见文字。"
        "subject_name_evidence 和 credit_code_evidence 请填写包含字段标签和值的原文片段，"
        "例如“名称：某某有限公司”；如果看不清或证据片段不存在，对应字段输出 null。"
        "source_page 输出营业执照所在页码，从 1 开始；ignored_pages 输出被忽略页的页码和原因。"
        "如果确认是营业执照，document_type 输出 business_license；无法识别的字段输出 null。"
        "不要编造证照上不存在的内容。日期尽量规范为 YYYY-MM-DD；长期有效 valid_to 输出 长期。"
    )


def _get_value(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def content_block_for_business_license_file(
    encoded_content: str,
    *,
    mime_type: str,
    file_name: str | None,
) -> dict[str, Any]:
    if mime_type == "application/pdf":
        return {
            "type": "file",
            "file": {
                "filename": file_name or "document.pdf",
                "file_data": f"data:{mime_type};base64,{encoded_content}",
            },
        }
    return {
        "type": "image",
        "source_type": "base64",
        "mime_type": mime_type,
        "data": encoded_content,
    }


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
