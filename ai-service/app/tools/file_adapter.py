from pathlib import Path
from typing import Protocol


class FileAdapter(Protocol):
    def read_bytes(self, path: str | Path) -> bytes:
        ...


class StubFileAdapter:
    implementation_status = "not_implemented"

    def read_bytes(self, path: str | Path) -> bytes:
        return b""
