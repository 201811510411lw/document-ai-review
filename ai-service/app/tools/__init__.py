"""Stub tool adapters for private deployment integrations."""

from app.tools.erp_adapter import StubErpAdapter
from app.tools.file_adapter import StubFileAdapter
from app.tools.image_adapter import StubImageAdapter
from app.tools.im_adapter import StubImAdapter
from app.tools.license_file_recognition import (
    LocalPdfDocumentLoadError,
    LocalPdfNotFoundError,
)
from app.tools.llm_adapter import StubLlmAdapter
from app.tools.oa_adapter import StubOaAdapter
from app.tools.pdf_adapter import StubPdfAdapter
from app.tools.vision_adapter import (
    FakeVisionAdapter,
    LangChainVisionAdapter,
    build_business_license_vision_adapter,
)

__all__ = [
    "LocalPdfDocumentLoadError",
    "LocalPdfNotFoundError",
    "StubErpAdapter",
    "StubFileAdapter",
    "StubImageAdapter",
    "StubImAdapter",
    "StubLlmAdapter",
    "StubOaAdapter",
    "StubPdfAdapter",
    "FakeVisionAdapter",
    "LangChainVisionAdapter",
    "build_business_license_vision_adapter",
]
