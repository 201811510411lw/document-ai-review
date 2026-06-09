from typing import Any, Protocol


class LlmAdapter(Protocol):
    def complete(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        ...


class StubLlmAdapter:
    implementation_status = "not_implemented"

    def complete(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "implementation_status": self.implementation_status,
            "content": "",
            "metadata": {},
        }
