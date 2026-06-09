from typing import Any, Protocol


class OcrAdapter(Protocol):
    def extract_text(self, source: Any) -> str:
        ...


class StubOcrAdapter:
    implementation_status = "not_implemented"

    def extract_text(self, source: Any) -> str:
        return ""
