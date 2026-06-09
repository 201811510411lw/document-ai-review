from typing import Protocol

from pydantic import BaseModel, Field

from app.models import ReviewInput


class LoadedDocument(BaseModel):
    text: str
    input_type: str
    metadata: dict[str, str] = Field(default_factory=dict)


class FoodLicenseOcrAdapter(Protocol):
    def extract_text(self, file_input: dict[str, object]) -> str:
        """Extract OCR text from an uploaded PDF/image boundary."""


class StubFoodLicenseOcrAdapter:
    def __init__(self, fixed_text: str = "") -> None:
        self.fixed_text = fixed_text

    def extract_text(self, file_input: dict[str, object]) -> str:
        return self.fixed_text


def load_food_license_document(
    review_input: ReviewInput,
    ocr_adapter: FoodLicenseOcrAdapter | None = None,
) -> LoadedDocument:
    if review_input.ocr_text and review_input.ocr_text.strip():
        return LoadedDocument(
            text=review_input.ocr_text.strip(),
            input_type="ocr_text",
            metadata={"source": "request.ocr_text"},
        )

    file_input = review_input.file.model_dump() if review_input.file else {}
    content_type = str(file_input.get("content_type", ""))
    adapter = ocr_adapter or StubFoodLicenseOcrAdapter(
        fixed_text=str(review_input.options.get("stub_ocr_text", ""))
    )
    return LoadedDocument(
        text=adapter.extract_text(file_input).strip(),
        input_type=_input_type_from_content_type(content_type),
        metadata={
            "filename": str(file_input.get("filename", "")),
            "content_type": content_type,
        },
    )


def _input_type_from_content_type(content_type: str) -> str:
    if content_type == "application/pdf":
        return "pdf"
    if content_type.startswith("image/"):
        return "image"
    return "file"
