from typing import Any, Protocol


class ErpAdapter(Protocol):
    def fetch_context(self, external_reference_id: str) -> dict[str, Any]:
        ...


class StubErpAdapter:
    implementation_status = "not_implemented"

    def fetch_context(self, external_reference_id: str) -> dict[str, Any]:
        return {
            "implementation_status": self.implementation_status,
            "context": {},
        }
