from pathlib import Path
from io import BytesIO
from tempfile import gettempdir
from typing import Any, Protocol

from pypdf import PdfReader
from app.tools.document_constraints import DocumentInputLimitError, enforce_pdf_page_limit


class DocumentLoader(Protocol):
    def load(self, source: Any) -> dict[str, Any]:
        ...


class StubDocumentLoader:
    implementation_status = "not_implemented"

    def load(self, source: Any) -> dict[str, Any]:
        stub_text = _get_value(source, "stub_text") or ""
        return {
            "implementation_status": self.implementation_status,
            "text": stub_text,
            "metadata": {
                "file_name": _get_value(source, "file_name"),
                "mime_type": _get_value(source, "mime_type"),
                "document_format": _get_value(source, "document_format")
                or _get_value(source, "file_type"),
                "local_path": _get_value(source, "local_path")
                or _get_value(source, "file_path"),
            },
        }


class LocalPdfDocumentLoader:
    implementation_status = "implemented"

    def load(self, source: Any) -> dict[str, Any]:
        local_path = _get_value(source, "local_path") or _get_value(source, "file_path")
        metadata = _metadata_from_source(source)
        metadata.update(
            {
                "implementation_status": self.implementation_status,
                "source": "local_path",
                "needs_ocr": False,
            }
        )

        path = _validate_local_pdf_path(local_path)
        text = _extract_pdf_text(path).strip()
        metadata["needs_ocr"] = not bool(text)
        return {
            "implementation_status": self.implementation_status,
            "text": text,
            "metadata": metadata,
        }

    def load_bytes(
        self,
        content: bytes,
        *,
        file_name: str | None = None,
        mime_type: str | None = None,
        document_format: str | None = None,
    ) -> dict[str, Any]:
        metadata = {
            "file_name": file_name,
            "mime_type": mime_type or "application/pdf",
            "document_format": document_format or "pdf",
            "local_path": None,
            "implementation_status": self.implementation_status,
            "source": "remote_content",
            "needs_ocr": False,
        }
        text = _extract_pdf_text_from_bytes(content).strip()
        metadata["needs_ocr"] = not bool(text)
        return {
            "implementation_status": self.implementation_status,
            "text": text,
            "metadata": metadata,
        }


class LocalPdfDocumentLoadError(ValueError):
    code = "LOCAL_PDF_LOAD_ERROR"
    message = "file.local_path 指向的 PDF 文件无法读取"


class LocalPdfNotFoundError(LocalPdfDocumentLoadError):
    code = "LOCAL_PDF_NOT_FOUND"
    message = "file.local_path 指向的 PDF 文件不存在"


class UnsafeLocalPdfPathError(LocalPdfDocumentLoadError):
    code = "UNSAFE_LOCAL_PDF_PATH"
    message = "file.local_path 不是允许的本地 PDF 文件路径"


def _metadata_from_source(source: Any) -> dict[str, Any]:
    return {
        "file_name": _get_value(source, "file_name"),
        "mime_type": _get_value(source, "mime_type"),
        "document_format": _get_value(source, "document_format")
        or _get_value(source, "file_type"),
        "local_path": _get_value(source, "local_path") or _get_value(source, "file_path"),
    }


def _validate_local_pdf_path(local_path: Any) -> Path:
    if not isinstance(local_path, str) or not local_path.strip():
        raise UnsafeLocalPdfPathError(UnsafeLocalPdfPathError.message)

    path = Path(local_path).expanduser()
    if not path.is_absolute():
        raise UnsafeLocalPdfPathError(UnsafeLocalPdfPathError.message)

    resolved_path = path.resolve(strict=False)
    if not resolved_path.exists() or not resolved_path.is_file():
        raise LocalPdfNotFoundError(LocalPdfNotFoundError.message)
    if resolved_path.suffix.lower() != ".pdf":
        raise UnsafeLocalPdfPathError(UnsafeLocalPdfPathError.message)
    if not _is_allowed_local_pdf_path(resolved_path):
        raise UnsafeLocalPdfPathError(UnsafeLocalPdfPathError.message)
    return resolved_path


def _extract_pdf_text(path: Path) -> str:
    try:
        reader = PdfReader(str(path))
        enforce_pdf_page_limit(len(reader.pages))
        page_texts = [page.extract_text() or "" for page in reader.pages]
    except LocalPdfDocumentLoadError:
        raise
    except DocumentInputLimitError:
        raise
    except Exception as error:
        raise LocalPdfDocumentLoadError(LocalPdfDocumentLoadError.message) from error
    return "\n".join(text for text in page_texts if text)


def _extract_pdf_text_from_bytes(content: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(content))
        enforce_pdf_page_limit(len(reader.pages))
        page_texts = [page.extract_text() or "" for page in reader.pages]
    except DocumentInputLimitError:
        raise
    except Exception as error:
        raise LocalPdfDocumentLoadError(LocalPdfDocumentLoadError.message) from error
    return "\n".join(text for text in page_texts if text)


def _is_allowed_local_pdf_path(path: Path) -> bool:
    allowed_roots = [
        Path.cwd().resolve(),
        Path(gettempdir()).resolve(),
    ]
    return any(path == root or root in path.parents for root in allowed_roots)


def _get_value(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)
