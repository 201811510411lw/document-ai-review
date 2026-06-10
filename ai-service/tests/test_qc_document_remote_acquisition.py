from app.tools.remote_document import (
    RemoteDocumentDownloadError,
    RemoteDocumentDownloader,
    UnsupportedRemoteDocumentTypeError,
)


class StubResponse:
    def __init__(self, status_code=200, content=b"%PDF-1.4", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}


class StubHttpClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.requests = []

    def get(self, url, timeout):
        self.requests.append({"url": url, "timeout": timeout})
        if self.error:
            raise self.error
        return self.response


def test_remote_downloader_downloads_pdf_and_detects_media_type():
    client = StubHttpClient(
        StubResponse(
            content=b"%PDF-1.4\nsample",
            headers={"Content-Type": "application/pdf"},
        )
    )
    downloader = RemoteDocumentDownloader(http_client=client)

    document = downloader.download("https://files.example.test/report.pdf")

    assert document.content == b"%PDF-1.4\nsample"
    assert document.file_type == "pdf"
    assert document.mime_type == "application/pdf"
    assert document.source_url == "https://files.example.test/report.pdf"
    assert client.requests == [
        {"url": "https://files.example.test/report.pdf", "timeout": 15}
    ]


def test_remote_downloader_supports_jpg_jpeg_and_png():
    cases = [
        ("https://files.example.test/report.jpg", "image/jpeg", "jpg"),
        ("https://files.example.test/report.jpeg", "image/jpeg", "jpeg"),
        ("https://files.example.test/report.png", "image/png", "png"),
    ]

    for url, content_type, expected_type in cases:
        document = RemoteDocumentDownloader(
            http_client=StubHttpClient(
                StubResponse(content=b"image-bytes", headers={"Content-Type": content_type})
            )
        ).download(url)

        assert document.file_type == expected_type
        assert document.mime_type == content_type


def test_remote_downloader_standardizes_403_and_404():
    for status_code in (403, 404):
        downloader = RemoteDocumentDownloader(
            http_client=StubHttpClient(StubResponse(status_code=status_code))
        )

        try:
            downloader.download(f"https://files.example.test/{status_code}.pdf")
        except RemoteDocumentDownloadError as error:
            assert error.code == f"REMOTE_DOCUMENT_HTTP_{status_code}"
            assert error.status_code == status_code
        else:
            raise AssertionError("HTTP error should be standardized")


def test_remote_downloader_standardizes_timeout():
    downloader = RemoteDocumentDownloader(
        http_client=StubHttpClient(error=TimeoutError("network timeout"))
    )

    try:
        downloader.download("https://files.example.test/timeout.pdf")
    except RemoteDocumentDownloadError as error:
        assert error.code == "REMOTE_DOCUMENT_TIMEOUT"
    else:
        raise AssertionError("timeout should be standardized")


def test_remote_downloader_rejects_empty_file():
    downloader = RemoteDocumentDownloader(
        http_client=StubHttpClient(
            StubResponse(content=b"", headers={"Content-Type": "application/pdf"})
        )
    )

    try:
        downloader.download("https://files.example.test/empty.pdf")
    except RemoteDocumentDownloadError as error:
        assert error.code == "REMOTE_DOCUMENT_EMPTY"
    else:
        raise AssertionError("empty download should be rejected")


def test_remote_downloader_rejects_header_extension_mismatch():
    downloader = RemoteDocumentDownloader(
        http_client=StubHttpClient(
            StubResponse(
                content=b"%PDF-1.4",
                headers={"Content-Type": "application/pdf"},
            )
        )
    )

    try:
        downloader.download("https://files.example.test/report.png")
    except UnsupportedRemoteDocumentTypeError as error:
        assert error.code == "REMOTE_DOCUMENT_TYPE_MISMATCH"
        assert error.detected_file_type == "pdf"
        assert error.extension_file_type == "png"
    else:
        raise AssertionError("header and extension mismatch should be explicit")
