from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.models import ReviewInput
from app.services.review_service import ReviewService, review_service

router = APIRouter(prefix="/api/v1/food-license", tags=["food-license"])


def get_review_service() -> ReviewService:
    return review_service


@router.post("/reviews")
def create_food_license_review(
    review_input: ReviewInput,
    service: ReviewService = Depends(get_review_service),
) -> dict[str, Any]:
    if not review_input.ocr_text.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "EMPTY_OCR_TEXT",
                "message": "ocr_text 不能为空",
            },
        )

    result = service.review_food_license(review_input)
    return result.model_dump(mode="json")
