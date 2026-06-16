from datetime import datetime
from typing import Any, Literal, Protocol

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.api.auth import require_web_console_user
from app.models import ReviewResult
from app.repositories import build_review_result_repository_from_env


router = APIRouter(prefix="/api/v1/qc", tags=["qc-reviews"])


class QcReviewRepository(Protocol):
    def list_qc_reviews(
        self,
        *,
        supplier_name: str | None = None,
        credit_code: str | None = None,
        document_type: str | None = None,
        risk_level: str | None = None,
        review_status: str | None = None,
        needs_manual_review: bool | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        ...

    def get_qc_review_detail(self, task_id: str) -> dict[str, Any] | None:
        ...

    def get_by_task_id(self, task_id: str) -> ReviewResult | None:
        ...

    def manual_review_qc_review(
        self,
        *,
        task_id: str,
        decision: str,
        comment: str,
        reviewer_id: str,
        reviewer_username: str,
        reviewed_at: datetime,
    ) -> dict[str, Any] | None:
        ...


class ManualReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    comment: str = Field(min_length=1, max_length=2000)
    reviewer_id: str = Field(min_length=1, max_length=128)

    @field_validator("comment", "reviewer_id")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


def get_qc_review_repository() -> QcReviewRepository:
    return build_review_result_repository_from_env()


@router.get("/reviews")
def list_qc_reviews(
    supplier_name: str | None = Query(default=None),
    credit_code: str | None = Query(default=None),
    document_type: str | None = Query(default=None),
    risk_level: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    needs_manual_review: bool | None = Query(default=None),
    created_from: str | None = Query(default=None),
    created_to: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _current_user: dict[str, Any] = Depends(require_web_console_user),
    repository: QcReviewRepository = Depends(get_qc_review_repository),
) -> dict[str, Any]:
    return repository.list_qc_reviews(
        supplier_name=_blank_to_none(supplier_name),
        credit_code=_blank_to_none(credit_code),
        document_type=_blank_to_none(document_type),
        risk_level=_blank_to_none(risk_level),
        review_status=_blank_to_none(review_status),
        needs_manual_review=needs_manual_review,
        created_from=_blank_to_none(created_from),
        created_to=_blank_to_none(created_to),
        page=page,
        page_size=page_size,
    )


@router.get("/reviews/{task_id}")
def get_qc_review_detail(
    task_id: str,
    _current_user: dict[str, Any] = Depends(require_web_console_user),
    repository: QcReviewRepository = Depends(get_qc_review_repository),
) -> dict[str, Any]:
    detail = repository.get_qc_review_detail(task_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "QC_REVIEW_NOT_FOUND",
                "message": "未找到 QC 审核结果",
            },
        )
    payload = repository.get_by_task_id(task_id)
    return {
        **detail,
        "payload": payload.model_dump(mode="json") if payload is not None else None,
    }


@router.post("/reviews/{task_id}/manual-review")
def manual_review_qc_review(
    task_id: str,
    request: ManualReviewRequest,
    current_user: dict[str, Any] = Depends(require_web_console_user),
    repository: QcReviewRepository = Depends(get_qc_review_repository),
) -> dict[str, Any]:
    reviewed_at = datetime.now().astimezone()
    detail = repository.manual_review_qc_review(
        task_id=task_id,
        decision=request.decision,
        comment=request.comment.strip(),
        reviewer_id=request.reviewer_id.strip(),
        reviewer_username=str(current_user.get("username") or ""),
        reviewed_at=reviewed_at,
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "QC_REVIEW_NOT_FOUND",
                "message": "未找到 QC 审核结果",
            },
        )
    payload = repository.get_by_task_id(task_id)
    return {
        **detail,
        "payload": payload.model_dump(mode="json") if payload is not None else None,
    }


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
