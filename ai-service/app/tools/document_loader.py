from typing import Any, Protocol


class DocumentLoader(Protocol):
    def load(self, source: Any) -> dict[str, Any]:
        ...


class StubDocumentLoader:
    implementation_status = "not_implemented"

    def load(self, source: Any) -> dict[str, Any]:
        return {
            "implementation_status": self.implementation_status,
            "text": "",
            "metadata": {},
        }
