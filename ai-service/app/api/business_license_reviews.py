from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.models import ReviewInput
from app.services.review_service import ReviewService, review_service
from app.tools.document_constraints import DocumentInputLimitError
from app.tools.license_file_recognition import LocalPdfDocumentLoadError


router = APIRouter(prefix="/api/v1/business-license", tags=["business-license"])


def get_review_service() -> ReviewService:
    return review_service


@router.post("/reviews")
def create_business_license_review(
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
    has_file_uri = bool((file_input.file_uri or "").strip()) if file_input else False

    if has_ocr_text or has_stub_text:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "UNSUPPORTED_TEXT_DOCUMENT_INPUT",
                "message": "营业执照审核不支持 ocr_text 或 file.stub_text，请提供 PDF/JPG/JPEG/PNG 文件",
            },
        )
    if not has_local_path and not has_file_uri:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "EMPTY_DOCUMENT_INPUT",
                "message": "file.local_path 或 file.file_uri 至少提供一个",
            },
        )

    try:
        result = service.review(review_input, use_case_name="business_license")
    except DocumentInputLimitError as error:
        raise HTTPException(
            status_code=400,
            detail={
                "code": error.code,
                "message": error.message,
            },
        ) from error
    except LocalPdfDocumentLoadError as error:
        raise HTTPException(
            status_code=400,
            detail={
                "code": error.code,
                "message": error.message,
            },
        ) from error
    return result.model_dump(mode="json")
