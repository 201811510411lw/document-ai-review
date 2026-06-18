import os
from typing import Any

from app.tools.aliyun_ocr_adapter import AliyunCloudMarketOcrAdapter


class AliyunOcrTextAdapter:
    implementation_status = "configured"

    def __init__(self, *, ocr_adapter: Any | None = None) -> None:
        self.ocr_adapter = ocr_adapter or AliyunCloudMarketOcrAdapter()
        self.provider = "aliyun_ocr_text"

    def extract_text(self, source: Any) -> dict[str, Any]:
        original_model = os.environ.get("ALIYUN_OCR_LLM_PARSE_MODEL")
        os.environ["ALIYUN_OCR_LLM_PARSE_MODEL"] = ""
        try:
            result = self.ocr_adapter.extract_text(source)
        finally:
            if original_model is None:
                os.environ.pop("ALIYUN_OCR_LLM_PARSE_MODEL", None)
            else:
                os.environ["ALIYUN_OCR_LLM_PARSE_MODEL"] = original_model

        metadata = dict(result.get("metadata") or {})
        metadata["provider"] = self.provider
        metadata["upstream_provider"] = "aliyun_cloud_market_ocr"
        metadata["structured_extraction"] = "aliyun_ocr_text_only"
        return {
            "text": result.get("text", ""),
            "metadata": metadata,
        }
