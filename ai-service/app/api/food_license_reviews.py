from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.models import ReviewInput
from app.services.review_service import ReviewService, review_service
from app.tools import LocalPdfDocumentLoadError

router = APIRouter(prefix="/api/v1/food-license", tags=["food-license"])


def get_review_service() -> ReviewService:
    return review_service


@router.post("/reviews")
def create_food_license_review(
    review_input: ReviewInput,
    service: ReviewService = Depends(get_review_service),
) -> dict[str, Any]:
    file_input = review_input.file or review_input.document
    has_ocr_text = bool((review_input.ocr_text or "").strip())
    has_stub_text = bool((file_input.stub_text or "").strip()) if file_input else False
    has_local_path = (
        bool(((file_input.local_path or file_input.file_path or "")).strip())
        if file_input
        else False
    )
    if has_ocr_text and (has_stub_text or has_local_path or file_input is not None):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "AMBIGUOUS_DOCUMENT_INPUT",
                "message": "ocr_text 和文件输入只能二选一",
            },
        )
    if not has_ocr_text and not has_stub_text and not has_local_path:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "EMPTY_DOCUMENT_INPUT",
                "message": "ocr_text、file.stub_text 或 file.local_path 至少提供一个",
            },
        )

    try:
        result = service.review_food_license(review_input)
    except LocalPdfDocumentLoadError as error:
        raise HTTPException(
            status_code=400,
            detail={
                "code": error.code,
                "message": error.message,
            },
        ) from error
    return result.model_dump(mode="json")
