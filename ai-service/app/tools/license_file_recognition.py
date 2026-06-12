from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

from pypdf import PdfReader

from app.tools.document_constraints import (
    enforce_file_size_limit,
    enforce_image_dimension_limit,
    enforce_pdf_page_limit,
)
from app.tools.remote_document import RemoteDocumentDownloadError, RemoteDocumentDownloader
from app.tools.vision_adapter import VisionInput


SUPPORTED_LICENSE_FILE_TYPES = {"pdf", "jpg", "jpeg", "png"}


class LocalFileRecognitionError(ValueError):
    code = "LOCAL_FILE_RECOGNITION_ERROR"
    message = "file.local_path 指向的文件无法读取"


class LocalPdfDocumentLoadError(LocalFileRecognitionError):
    code = "LOCAL_PDF_LOAD_ERROR"
    message = "file.local_path 指向的 PDF 文件无法读取"


class LocalPdfNotFoundError(LocalPdfDocumentLoadError):
    code = "LOCAL_PDF_NOT_FOUND"
    message = "file.local_path 指向的 PDF 文件不存在"


class LlmFileAdapter(Protocol):
    def extract_text(self, source: Any) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class LicenseDocumentInput:
    input_type: str
    file_name: str | None = None
    mime_type: str | None = None
    document_format: str | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class LicenseFileRecognitionResult:
    document_input: LicenseDocumentInput
    document_text: str = ""
    structured_fields: dict[str, Any] = field(default_factory=dict)
    extraction_metadata: dict[str, Any] = field(default_factory=dict)


def recognize_license_file(
    review_input: Any,
    *,
    adapter: LlmFileAdapter,
    downloader: RemoteDocumentDownloader | None = None,
    include_legacy_vision_metadata: bool = False,
) -> LicenseFileRecognitionResult:
    file_input = review_input.file or review_input.document
    if (review_input.ocr_text or "").strip():
        return _unsupported_text_result()
    if file_input is not None and (file_input.stub_text or "").strip():
        return _unsupported_text_result(file_input)
    if file_input is None:
        return _empty_result()

    local_path = file_input.local_path or file_input.file_path
    if local_path:
        return _recognize_local_file(
            file_input,
            local_path=local_path,
            adapter=adapter,
            include_legacy_vision_metadata=include_legacy_vision_metadata,
        )
    if file_input.file_uri:
        return _recognize_remote_file(
            file_input,
            adapter=adapter,
            downloader=downloader or RemoteDocumentDownloader(),
            include_legacy_vision_metadata=include_legacy_vision_metadata,
        )
    return _empty_result()


def _recognize_local_file(
    file_input: Any,
    *,
    local_path: str,
    adapter: LlmFileAdapter,
    include_legacy_vision_metadata: bool,
) -> LicenseFileRecognitionResult:
    try:
        path = Path(local_path).expanduser().resolve(strict=True)
    except FileNotFoundError as error:
        raise LocalPdfNotFoundError(LocalPdfNotFoundError.message) from error

    enforce_file_size_limit(path.stat().st_size)
    content = path.read_bytes()
    mime_type = file_input.mime_type or _mime_type_from_path(path)
    document_format = _normalize_document_format(
        file_input.document_format or file_input.file_type,
        mime_type=mime_type,
    )
    if document_format not in SUPPORTED_LICENSE_FILE_TYPES:
        return LicenseFileRecognitionResult(
            document_input=LicenseDocumentInput(
                input_type=document_format or "file",
                file_name=file_input.file_name,
                mime_type=mime_type,
                document_format=document_format,
                source_url=file_input.file_uri,
            ),
            extraction_metadata={"local_document": {"unsupported_format": True}},
        )

    _enforce_content_limits(content, document_format)
    recognition_result = adapter.extract_text(
        VisionInput(
            content=content,
            mime_type=mime_type,
            file_name=file_input.file_name,
            source_url=file_input.file_uri,
        )
    )
    return _recognition_result(
        recognition_result,
        document_input=LicenseDocumentInput(
            input_type="pdf" if document_format == "pdf" else "image",
            file_name=file_input.file_name,
            mime_type=mime_type,
            document_format=document_format,
            source_url=file_input.file_uri,
        ),
        include_legacy_vision_metadata=include_legacy_vision_metadata,
    )


def _recognize_remote_file(
    file_input: Any,
    *,
    adapter: LlmFileAdapter,
    downloader: RemoteDocumentDownloader,
    include_legacy_vision_metadata: bool,
) -> LicenseFileRecognitionResult:
    try:
        remote_document = downloader.download(file_input.file_uri)
    except RemoteDocumentDownloadError as error:
        return LicenseFileRecognitionResult(
            document_input=LicenseDocumentInput(
                input_type="remote_error",
                file_name=file_input.file_name,
                source_url=file_input.file_uri,
            ),
            extraction_metadata={
                "remote_document_error": {
                    "code": error.code,
                    "source_url": error.source_url,
                    "status_code": error.status_code,
                }
            },
        )

    if remote_document.file_type not in SUPPORTED_LICENSE_FILE_TYPES:
        return LicenseFileRecognitionResult(
            document_input=LicenseDocumentInput(
                input_type=remote_document.file_type,
                file_name=file_input.file_name,
                mime_type=remote_document.mime_type,
                document_format=remote_document.file_type,
                source_url=remote_document.source_url,
            ),
            extraction_metadata={
                "remote_document": {
                    "status_code": remote_document.status_code,
                    "file_type": remote_document.file_type,
                    "mime_type": remote_document.mime_type,
                    "unsupported_format": True,
                }
            },
        )

    enforce_file_size_limit(len(remote_document.content))
    _enforce_content_limits(remote_document.content, remote_document.file_type)
    recognition_result = adapter.extract_text(
        VisionInput(
            content=remote_document.content,
            mime_type=remote_document.mime_type,
            file_name=file_input.file_name,
            source_url=remote_document.source_url,
        )
    )
    result = _recognition_result(
        recognition_result,
        document_input=LicenseDocumentInput(
            input_type="pdf" if remote_document.file_type == "pdf" else "image",
            file_name=file_input.file_name,
            mime_type=remote_document.mime_type,
            document_format=remote_document.file_type,
            source_url=remote_document.source_url,
        ),
        include_legacy_vision_metadata=include_legacy_vision_metadata,
    )
    return LicenseFileRecognitionResult(
        document_input=result.document_input,
        document_text=result.document_text,
        structured_fields=result.structured_fields,
        extraction_metadata={
            "remote_document": {
                "status_code": remote_document.status_code,
                "file_type": remote_document.file_type,
                "mime_type": remote_document.mime_type,
                "needs_llm_file_recognition": True,
            },
            **result.extraction_metadata,
        },
    )


def _recognition_result(
    recognition_result: dict[str, Any],
    *,
    document_input: LicenseDocumentInput,
    include_legacy_vision_metadata: bool,
) -> LicenseFileRecognitionResult:
    metadata = recognition_result.get("metadata", {})
    extraction_metadata = {"llm_file_extractor": metadata}
    if include_legacy_vision_metadata:
        extraction_metadata["vision_extractor"] = metadata
    return LicenseFileRecognitionResult(
        document_input=document_input,
        document_text=(recognition_result.get("text") or "").strip(),
        structured_fields=recognition_result.get("structured_fields") or {},
        extraction_metadata=extraction_metadata,
    )


def _unsupported_text_result(file_input: Any | None = None) -> LicenseFileRecognitionResult:
    return LicenseFileRecognitionResult(
        document_input=LicenseDocumentInput(
            input_type="unsupported_text",
            file_name=getattr(file_input, "file_name", None),
            mime_type=getattr(file_input, "mime_type", None),
            document_format=(
                getattr(file_input, "document_format", None)
                or getattr(file_input, "file_type", None)
            ),
            source_url=getattr(file_input, "file_uri", None),
        ),
        extraction_metadata={
            "input_error": {"code": "UNSUPPORTED_TEXT_DOCUMENT_INPUT"},
        },
    )


def _empty_result() -> LicenseFileRecognitionResult:
    return LicenseFileRecognitionResult(
        document_input=LicenseDocumentInput(input_type="empty"),
        extraction_metadata={"input_error": {"code": "EMPTY_DOCUMENT_INPUT"}},
    )


def _enforce_content_limits(content: bytes, document_format: str) -> None:
    if document_format == "pdf":
        reader = PdfReader(BytesIO(content))
        enforce_pdf_page_limit(len(reader.pages))
    else:
        enforce_image_dimension_limit(content)


def _document_format_from_mime_type(mime_type: str | None) -> str | None:
    if mime_type == "application/pdf":
        return "pdf"
    if mime_type == "image/jpeg":
        return "jpeg"
    if mime_type == "image/png":
        return "png"
    return None


def _normalize_document_format(
    declared_format: str | None,
    *,
    mime_type: str | None,
) -> str | None:
    if declared_format in {None, "", "image"}:
        return _document_format_from_mime_type(mime_type)
    return declared_format


def _mime_type_from_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    return "application/octet-stream"
