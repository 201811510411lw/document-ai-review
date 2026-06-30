from dataclasses import dataclass, field
from io import BytesIO
import os
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.tools.document_constraints import (
    DocumentInputLimitError,
    enforce_file_size_limit,
)
from app.tools.remote_document import RemoteDocumentDownloadError, RemoteDocumentDownloader


@dataclass(frozen=True)
class DocumentTextAcquisitionResult:
    document_text: str
    document_input: dict[str, Any]
    extraction_metadata: dict[str, Any] = field(default_factory=dict)


def acquire_document_text(
    review_input: Any,
    *,
    downloader: Any | None = None,
) -> DocumentTextAcquisitionResult:
    ocr_text = (getattr(review_input, "ocr_text", None) or "").strip()
    if ocr_text:
        return DocumentTextAcquisitionResult(
            document_text=ocr_text,
            document_input={"input_type": "ocr_text"},
        )

    file_input = getattr(review_input, "file", None) or getattr(review_input, "document", None)
    stub_text = ((getattr(file_input, "stub_text", None) or "") if file_input else "").strip()
    if stub_text:
        return DocumentTextAcquisitionResult(
            document_text=stub_text,
            document_input={
                "input_type": "stub_text",
                "file_name": getattr(file_input, "file_name", None),
                "mime_type": getattr(file_input, "mime_type", None),
                "document_format": _document_format_from_file_input(file_input),
                "source_url": getattr(file_input, "file_uri", None),
            },
        )
    if file_input is None:
        return DocumentTextAcquisitionResult(
            document_text="",
            document_input={"input_type": "empty"},
        )

    local_path = getattr(file_input, "local_path", None) or getattr(file_input, "file_path", None)
    if local_path:
        return _acquire_local_file_text(file_input, local_path=local_path)
    file_uri = getattr(file_input, "file_uri", None)
    if file_uri:
        return _acquire_remote_file_text(
            file_input,
            downloader=downloader or RemoteDocumentDownloader(),
        )
    return DocumentTextAcquisitionResult(
        document_text="",
        document_input={
            "input_type": "empty",
            "file_name": getattr(file_input, "file_name", None),
            "mime_type": getattr(file_input, "mime_type", None),
            "document_format": _document_format_from_file_input(file_input),
            "source_url": getattr(file_input, "file_uri", None),
        },
    )


def _acquire_remote_file_text(
    file_input: Any,
    *,
    downloader: Any,
) -> DocumentTextAcquisitionResult:
    file_uri = getattr(file_input, "file_uri", None)
    try:
        remote_document = downloader.download(file_uri)
    except RemoteDocumentDownloadError as error:
        return DocumentTextAcquisitionResult(
            document_text="",
            document_input={
                "input_type": "remote_error",
                "file_name": getattr(file_input, "file_name", None),
                "source_url": file_uri,
            },
            extraction_metadata={
                "remote_document_error": {
                    "code": error.code,
                    "source_url": error.source_url,
                    "status_code": error.status_code,
                }
            },
        )

    enforce_file_size_limit(len(remote_document.content))
    if remote_document.file_type != "pdf":
        return DocumentTextAcquisitionResult(
            document_text="",
            document_input={
                "input_type": "remote_unsupported_text",
                "file_name": getattr(file_input, "file_name", None),
                "mime_type": remote_document.mime_type,
                "document_format": remote_document.file_type,
                "source_url": remote_document.source_url,
            },
            extraction_metadata={
                "remote_document": {
                    "status_code": remote_document.status_code,
                    "file_type": remote_document.file_type,
                    "mime_type": remote_document.mime_type,
                    "needs_ocr_fallback": True,
                }
            },
        )

    pdf_result = _extract_pdf_text(remote_document.content)
    has_text = bool(pdf_result["text"])
    return DocumentTextAcquisitionResult(
        document_text=pdf_result["text"],
        document_input={
            "input_type": "remote_pdf_text" if has_text else "remote_pdf_empty_text",
            "file_name": getattr(file_input, "file_name", None),
            "mime_type": remote_document.mime_type,
            "document_format": remote_document.file_type,
            "source_url": remote_document.source_url,
        },
        extraction_metadata={
            "remote_document": {
                "status_code": remote_document.status_code,
                "file_type": remote_document.file_type,
                "mime_type": remote_document.mime_type,
            },
            "pdf_text_extractor": pdf_result["metadata"],
        },
    )


def _acquire_local_file_text(file_input: Any, *, local_path: str) -> DocumentTextAcquisitionResult:
    path = Path(local_path).expanduser().resolve(strict=True)
    content = path.read_bytes()
    enforce_file_size_limit(len(content))
    document_format = _document_format_from_file_input(file_input) or _document_format_from_path(path)
    if document_format != "pdf":
        return DocumentTextAcquisitionResult(
            document_text="",
            document_input={
                "input_type": "local_unsupported_text",
                "file_name": getattr(file_input, "file_name", None),
                "mime_type": getattr(file_input, "mime_type", None),
                "document_format": document_format,
                "source_url": getattr(file_input, "file_uri", None),
            },
            extraction_metadata={"local_document": {"needs_ocr_fallback": True}},
        )
    pdf_result = _extract_pdf_text(content)
    has_text = bool(pdf_result["text"])
    return DocumentTextAcquisitionResult(
        document_text=pdf_result["text"],
        document_input={
            "input_type": "pdf_text" if has_text else "pdf_empty_text",
            "file_name": getattr(file_input, "file_name", None),
            "mime_type": getattr(file_input, "mime_type", None) or "application/pdf",
            "document_format": "pdf",
            "source_url": getattr(file_input, "file_uri", None),
        },
        extraction_metadata={"pdf_text_extractor": pdf_result["metadata"]},
    )


def _extract_pdf_text(content: bytes) -> dict[str, Any]:
    try:
        reader = PdfReader(BytesIO(content))
        page_count = len(reader.pages)
        _enforce_product_report_pdf_page_limit(page_count)
    except DocumentInputLimitError as error:
        return {
            "text": "",
            "metadata": {
                "method": "pypdf_text_layer",
                "status": "limit_error",
                "error_code": error.code,
                "error_message": error.message,
                "needs_ocr_fallback": False,
                "needs_manual_review": True,
            },
        }
    except (PdfReadError, Exception) as error:
        return {
            "text": "",
            "metadata": {
                "method": "pypdf_text_layer",
                "status": "parse_error",
                "error_type": type(error).__name__,
                "needs_ocr_fallback": True,
                "needs_manual_review": True,
            },
        }
    page_texts: list[str] = []
    pages_with_text = 0
    for page in reader.pages:
        page_text = (page.extract_text() or "").strip()
        if page_text:
            pages_with_text += 1
            page_texts.append(page_text)
    text = "\n\n".join(page_texts).strip()
    status = "extracted" if text else "empty_text_layer"
    return {
        "text": text,
        "metadata": {
            "method": "pypdf_text_layer",
            "status": status,
            "page_count": page_count,
            "pages_with_text": pages_with_text,
            "needs_ocr_fallback": not bool(text),
        },
    }


def _enforce_product_report_pdf_page_limit(page_count: int) -> None:
    max_pages = int(os.environ.get("QC_PRODUCT_REPORT_MAX_PDF_PAGES", "20"))
    if page_count > max_pages:
        raise DocumentInputLimitError(
            "QC_PRODUCT_REPORT_PDF_TOO_MANY_PAGES",
            "商品报告 PDF 页数超过限制",
        )


def _document_format_from_file_input(file_input: Any) -> str | None:
    value = (
        getattr(file_input, "document_format", None)
        or getattr(file_input, "file_type", None)
        or _document_format_from_name(getattr(file_input, "file_name", None))
    )
    return str(value).lower().lstrip(".") if value else None


def _document_format_from_path(path: Path) -> str | None:
    return _document_format_from_name(path.name)


def _document_format_from_name(file_name: str | None) -> str | None:
    if not file_name:
        return None
    suffix = Path(file_name).suffix.lower().lstrip(".")
    return suffix or None
