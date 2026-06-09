from typing import Any, Protocol


class LlmAdapter(Protocol):
    def complete(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        ...

    def complete_missing_fields(
        self,
        *,
        document_text: str,
        extracted_fields: Any,
        missing_fields: list[str],
    ) -> dict[str, Any]:
        ...


class StubLlmAdapter:
    implementation_status = "not_implemented"

    def complete(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "implementation_status": self.implementation_status,
            "content": "",
            "metadata": {},
        }

    def complete_missing_fields(
        self,
        *,
        document_text: str,
        extracted_fields: Any,
        missing_fields: list[str],
    ) -> dict[str, Any]:
        return {}
