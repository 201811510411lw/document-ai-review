from typing import Any, Protocol


class ImAdapter(Protocol):
    def notify(self, channel: str, payload: dict[str, Any]) -> dict[str, Any]:
        ...


class StubImAdapter:
    implementation_status = "not_implemented"

    def notify(self, channel: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "implementation_status": self.implementation_status,
            "channel": channel,
        }
