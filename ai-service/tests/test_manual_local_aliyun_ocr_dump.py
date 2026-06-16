import json
import os
from pathlib import Path

import pytest

from app.core.config import load_local_env
from app.tools.aliyun_ocr_adapter import AliyunCloudMarketOcrAdapter
from app.tools.vision_adapter import VisionInput


pytestmark = pytest.mark.manual


def test_manual_local_file_aliyun_ocr_dump():
    load_local_env()
    _require_env("ALIYUN_OCR_API_URL")
    _require_env("ALIYUN_OCR_APPCODE")
    local_file = Path(
        os.environ.get(
            "ALIYUN_OCR_LOCAL_FILE",
            "/home/lsym005226/project/document-ai-review/docs/a.pdf",
        )
    )
    if not local_file.exists():
        pytest.skip(f"ALIYUN_OCR_LOCAL_FILE does not exist: {local_file}")

    result = AliyunCloudMarketOcrAdapter().extract_text(
        VisionInput(
            content=local_file.read_bytes(),
            mime_type=_mime_type(local_file),
            file_name=local_file.name,
        )
    )
    _print_json(
        {
            "local_file": str(local_file),
            "result": result,
        }
    )

    assert result["text"]
    assert result["structured_fields"]


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.skip(f"{name} is required in local .env for this manual test")
    return value


def _mime_type(path: Path) -> str:
    mime_type = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".bmp": "image/bmp",
    }.get(path.suffix.lower(), "application/octet-stream")
    return mime_type


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
