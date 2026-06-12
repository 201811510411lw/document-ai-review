import base64
import os
from typing import Any

from app.tools.vision_adapter import parse_business_license_vision_json


class OpenAiFileAdapter:
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
                                "text": "请从输入文件中提取结构化 JSON，只输出 JSON 对象。",
                            },
                            content_block_for_file(
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

        content_text = str(getattr(response, "content", "") or "").strip()
        structured_fields = parse_business_license_vision_json(content_text)
        metadata = {
            "implementation_status": self.implementation_status,
            "provider": self.provider,
            "model": self.model,
        }
        if structured_fields is None:
            metadata["error_code"] = "VISION_EXTRACTOR_STRUCTURED_JSON_MISSING"
            metadata["raw_response_preview"] = content_text[:500]
        result = {"text": content_text, "metadata": metadata}
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
        return {"text": "", "metadata": metadata}


def content_block_for_file(
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


def _get_value(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)
