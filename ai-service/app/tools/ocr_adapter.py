from typing import Any, Protocol


class OcrAdapter(Protocol):
    def extract_text(self, source: Any) -> str:
        ...


class StubOcrAdapter:
    implementation_status = "not_implemented"

    def extract_text(self, source: Any) -> str:
        return _get_value(source, "stub_text") or ""


def _get_value(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)
