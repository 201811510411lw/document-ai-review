"""Stub tool adapters for private deployment integrations."""

from app.tools.document_loader import StubDocumentLoader
from app.tools.erp_adapter import StubErpAdapter
from app.tools.file_adapter import StubFileAdapter
from app.tools.image_adapter import StubImageAdapter
from app.tools.im_adapter import StubImAdapter
from app.tools.llm_adapter import StubLlmAdapter
from app.tools.oa_adapter import StubOaAdapter
from app.tools.ocr_adapter import StubOcrAdapter
from app.tools.pdf_adapter import StubPdfAdapter

__all__ = [
    "StubDocumentLoader",
    "StubErpAdapter",
    "StubFileAdapter",
    "StubImageAdapter",
    "StubImAdapter",
    "StubLlmAdapter",
    "StubOaAdapter",
    "StubOcrAdapter",
    "StubPdfAdapter",
]
