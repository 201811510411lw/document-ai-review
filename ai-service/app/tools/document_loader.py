from typing import Any, Protocol


class DocumentLoader(Protocol):
    def load(self, source: Any) -> dict[str, Any]:
        ...


class StubDocumentLoader:
    implementation_status = "not_implemented"

    def load(self, source: Any) -> dict[str, Any]:
        stub_text = _get_value(source, "stub_text") or ""
        return {
            "implementation_status": self.implementation_status,
            "text": stub_text,
            "metadata": {
                "file_name": _get_value(source, "file_name"),
                "mime_type": _get_value(source, "mime_type"),
                "document_format": _get_value(source, "document_format")
                or _get_value(source, "file_type"),
            },
        }


def _get_value(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)
