from typing import Protocol


class ImageAdapter(Protocol):
    def normalize(self, content: bytes) -> bytes:
        ...


class StubImageAdapter:
    implementation_status = "not_implemented"

    def normalize(self, content: bytes) -> bytes:
        return b""
