from typing import Protocol


class PdfAdapter(Protocol):
    def extract_text(self, content: bytes) -> str:
        ...


class StubPdfAdapter:
    implementation_status = "not_implemented"

    def extract_text(self, content: bytes) -> str:
        return ""
