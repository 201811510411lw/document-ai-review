import os
import base64
import json
from typing import Any, Protocol


class VisionAdapter(Protocol):
    implementation_status: str

    def extract_text(self, source: Any) -> dict[str, Any]:
        ...


class FakeVisionAdapter:
    implementation_status = "fake"

    def extract_text(self, source: Any) -> dict[str, Any]:
        structured_json = os.environ.get("BUSINESS_LICENSE_FAKE_VISION_JSON", "").strip()
        text = os.environ.get("BUSINESS_LICENSE_FAKE_VISION_TEXT", "").strip()
        metadata = {
            "implementation_status": self.implementation_status,
            "provider": "fake",
            "model": "fake-business-license-vision",
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

        model = ChatOpenAI(
            model=self.model,
            api_key=api_key,
            base_url=self.base_url or os.environ.get("OPENAI_BASE_URL"),
            timeout=self.timeout,
        )
        encoded_content = base64.b64encode(content).decode("ascii")
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
        result = {
            "text": content,
            "metadata": {
                "implementation_status": self.implementation_status,
                "provider": self.provider,
                "model": self.model,
            },
        }
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


def _business_license_prompt() -> str:
    return (
        "请从输入的营业执照图片或PDF中提取字段，只输出JSON对象，不要输出Markdown。"
        "字段包括 document_type, subject_name, credit_code, business_address, "
        "legal_person, established_date, valid_from, valid_to, issue_authority, issue_date。"
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
            "source_type": "base64",
            "mime_type": mime_type,
            "data": encoded_content,
            "filename": file_name or "document.pdf",
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
