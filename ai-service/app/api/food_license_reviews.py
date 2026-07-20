from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import require_web_console_user
from app.api.business_license_reviews import _review_response
from app.integrations.mysql_client import MySqlFetchClient, mysql_settings_from_env
from app.integrations.srm.food_license_tasks import (
    FoodLicenseSourceTaskError,
    SqlFetchClient,
    fetch_one_food_license_source_task,
)
from app.models import ReviewInput
from app.services.review_service import ReviewService, review_service
from app.tools.document_constraints import DocumentInputLimitError
from app.tools.license_file_recognition import LocalPdfDocumentLoadError

router = APIRouter(prefix="/api/v1/food-license", tags=["food-license"])


def get_review_service() -> ReviewService:
    return review_service


def get_srm_sql_client() -> SqlFetchClient:
    return MySqlFetchClient(mysql_settings_from_env("STARROCKS"))


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
    has_file_uri = bool((file_input.file_uri or "").strip()) if file_input else False
    if has_ocr_text or has_stub_text:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "UNSUPPORTED_TEXT_DOCUMENT_INPUT",
                "message": "食品许可证审核不支持 ocr_text 或 file.stub_text，请提供 PDF/JPG/JPEG/PNG 文件",
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
        result = service.review_food_license(review_input)
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


@router.post("/reviews/from-srm")
def create_food_license_review_from_srm(
    _current_user: dict[str, Any] = Depends(require_web_console_user),
    sql_client: SqlFetchClient = Depends(get_srm_sql_client),
    service: ReviewService = Depends(get_review_service),
) -> dict[str, Any]:
    try:
        task = fetch_one_food_license_source_task(sql_client)
    except FoodLicenseSourceTaskError as error:
        raise HTTPException(
            status_code=400,
            detail={
                "code": error.code,
                "message": str(error),
                "record_id": error.record_id,
            },
        ) from error

    if task is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "FOOD_LICENSE_SOURCE_RECORD_NOT_FOUND",
                "message": "未找到可审核的食品经营许可证来源记录",
            },
        )

    try:
        result = service.review(
            task.review_input,
            use_case_name=task.review_input.declared_document_type,
        )
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
    return _review_response(result)
