from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.models import ManualReviewAction, ReviewInput
from app.services.review_service import ReviewService, review_service

router = APIRouter(prefix="/api/v1/food-license", tags=["food-license"])


def get_review_service() -> ReviewService:
    return review_service


@router.post("/reviews")
def create_food_license_review(
    review_input: ReviewInput,
    service: ReviewService = Depends(get_review_service),
) -> dict[str, Any]:
    has_ocr_text = bool(review_input.ocr_text and review_input.ocr_text.strip())
    has_file = review_input.file is not None
    if not has_ocr_text and not has_file:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "EMPTY_OCR_TEXT",
                "message": "ocr_text 或 file 不能为空",
            },
        )

    result = service.review_food_license(review_input)
    return result.model_dump(mode="json")


@router.get("/reviews/{task_id}")
def get_food_license_review(
    task_id: str,
    service: ReviewService = Depends(get_review_service),
) -> dict[str, Any]:
    result = service.get_review(task_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "REVIEW_TASK_NOT_FOUND",
                "message": "审核任务不存在",
            },
        )
    return result.model_dump(mode="json")


@router.post("/reviews/{task_id}/manual-review")
def submit_food_license_manual_review(
    task_id: str,
    manual_review_action: ManualReviewAction,
    service: ReviewService = Depends(get_review_service),
) -> dict[str, Any]:
    result = service.submit_manual_review(task_id, manual_review_action)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "REVIEW_TASK_NOT_FOUND",
                "message": "审核任务不存在",
            },
        )
    return result.model_dump(mode="json")
