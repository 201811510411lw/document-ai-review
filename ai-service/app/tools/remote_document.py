from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

import httpx


SUPPORTED_REMOTE_DOCUMENT_TYPES = {"pdf", "jpg", "jpeg", "png"}

CONTENT_TYPE_TO_FILE_TYPE = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
}

FILE_TYPE_TO_MIME_TYPE = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}


@dataclass(frozen=True)
class RemoteDocument:
    source_url: str
    content: bytes
    file_type: str
    mime_type: str
    status_code: int
    headers: dict[str, str]


class RemoteDocumentDownloadError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
        source_url: str | None = None,
    ):
        self.code = code
        self.status_code = status_code
        self.source_url = source_url
        super().__init__(message)


class UnsupportedRemoteDocumentTypeError(RemoteDocumentDownloadError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        detected_file_type: str | None = None,
        extension_file_type: str | None = None,
        source_url: str | None = None,
    ):
        self.detected_file_type = detected_file_type
        self.extension_file_type = extension_file_type
        super().__init__(code, message, source_url=source_url)


class RemoteDocumentDownloader:
    def __init__(self, http_client: Any | None = None, timeout: int = 15):
        self.http_client = http_client or httpx.Client(follow_redirects=True)
        self.timeout = timeout

    def download(self, file_url: str) -> RemoteDocument:
        try:
            response = self.http_client.get(file_url, timeout=self.timeout)
        except TimeoutError as error:
            raise RemoteDocumentDownloadError(
                "REMOTE_DOCUMENT_TIMEOUT",
                "远程文件下载超时",
                source_url=file_url,
            ) from error
        except httpx.TimeoutException as error:
            raise RemoteDocumentDownloadError(
                "REMOTE_DOCUMENT_TIMEOUT",
                "远程文件下载超时",
                source_url=file_url,
            ) from error
        except Exception as error:
            raise RemoteDocumentDownloadError(
                "REMOTE_DOCUMENT_DOWNLOAD_FAILED",
                "远程文件下载失败",
                source_url=file_url,
            ) from error

        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code != 200:
            raise RemoteDocumentDownloadError(
                f"REMOTE_DOCUMENT_HTTP_{status_code}",
                f"远程文件下载返回 HTTP {status_code}",
                status_code=status_code,
                source_url=file_url,
            )

        content = getattr(response, "content", b"") or b""
        if not content:
            raise RemoteDocumentDownloadError(
                "REMOTE_DOCUMENT_EMPTY",
                "远程文件内容为空",
                status_code=status_code,
                source_url=file_url,
            )

        headers = _normalize_headers(getattr(response, "headers", {}) or {})
        content_type = _normalize_content_type(headers.get("content-type"))
        detected_file_type = _detect_type_from_content_type(content_type)
        extension_file_type = _detect_type_from_url(file_url)
        file_type = _resolve_file_type(
            detected_file_type=detected_file_type,
            extension_file_type=extension_file_type,
            source_url=file_url,
        )

        return RemoteDocument(
            source_url=file_url,
            content=content,
            file_type=file_type,
            mime_type=content_type or FILE_TYPE_TO_MIME_TYPE[file_type],
            status_code=status_code,
            headers=headers,
        )


def _resolve_file_type(
    *,
    detected_file_type: str | None,
    extension_file_type: str | None,
    source_url: str,
) -> str:
    if detected_file_type and extension_file_type:
        comparable_detected = "jpg" if detected_file_type == "jpeg" else detected_file_type
        comparable_extension = (
            "jpg" if extension_file_type == "jpeg" else extension_file_type
        )
        if comparable_detected != comparable_extension:
            raise UnsupportedRemoteDocumentTypeError(
                "REMOTE_DOCUMENT_TYPE_MISMATCH",
                "远程文件 Content-Type 与扩展名不一致",
                detected_file_type=detected_file_type,
                extension_file_type=extension_file_type,
                source_url=source_url,
            )
        return extension_file_type

    file_type = detected_file_type or extension_file_type
    if file_type in SUPPORTED_REMOTE_DOCUMENT_TYPES:
        return file_type
    raise UnsupportedRemoteDocumentTypeError(
        "REMOTE_DOCUMENT_UNSUPPORTED_TYPE",
        "远程文件类型不支持",
        detected_file_type=detected_file_type,
        extension_file_type=extension_file_type,
        source_url=source_url,
    )


def _normalize_headers(headers: Any) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in dict(headers).items()}


def _normalize_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    return content_type.split(";", 1)[0].strip().lower()


def _detect_type_from_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    return CONTENT_TYPE_TO_FILE_TYPE.get(content_type)


def _detect_type_from_url(file_url: str) -> str | None:
    parsed_path = urlparse(file_url).path
    suffix = PurePosixPath(parsed_path).suffix.lower().lstrip(".")
    if suffix in SUPPORTED_REMOTE_DOCUMENT_TYPES:
        return suffix
    return None
