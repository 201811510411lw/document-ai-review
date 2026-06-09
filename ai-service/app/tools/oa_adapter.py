from typing import Any, Protocol


class OaAdapter(Protocol):
    def write_back_review(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        ...


class StubOaAdapter:
    implementation_status = "not_implemented"

    def write_back_review(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "implementation_status": self.implementation_status,
            "task_id": task_id,
        }
