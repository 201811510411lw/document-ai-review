import os
from io import BytesIO


class DocumentInputLimitError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def enforce_file_size_limit(content_length: int) -> None:
    max_bytes = int(os.environ.get("BUSINESS_LICENSE_MAX_FILE_BYTES", str(20 * 1024 * 1024)))
    if content_length > max_bytes:
        raise DocumentInputLimitError(
            "DOCUMENT_FILE_TOO_LARGE",
            "营业执照文件超过大小限制",
        )


def enforce_pdf_page_limit(page_count: int) -> None:
    max_pages = int(os.environ.get("BUSINESS_LICENSE_MAX_PDF_PAGES", "3"))
    if page_count > max_pages:
        raise DocumentInputLimitError(
            "DOCUMENT_PDF_TOO_MANY_PAGES",
            "营业执照 PDF 页数超过限制",
        )


def enforce_image_dimension_limit(content: bytes) -> None:
    try:
        from PIL import Image

        image = Image.open(BytesIO(content))
        width, height = image.size
    except Exception:
        return
    max_pixels = int(os.environ.get("BUSINESS_LICENSE_MAX_IMAGE_PIXELS", "25000000"))
    if width * height > max_pixels:
        raise DocumentInputLimitError(
            "DOCUMENT_IMAGE_TOO_LARGE",
            "营业执照图片分辨率超过限制",
        )
