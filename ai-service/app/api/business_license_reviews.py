from datetime import datetime
from typing import Any, Literal, Protocol

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.api.auth import require_web_console_user
from app.integrations.mysql_client import MySqlFetchClient, mysql_settings_from_env
from app.integrations.srm.business_license_tasks import (
    BusinessLicenseSourceTaskError,
    SqlFetchClient,
    fetch_one_business_license_source_task,
)
from app.models import ReviewInput, ReviewResult
from app.repositories import build_review_result_repository_from_env
from app.services.review_service import ReviewService, review_service
from app.tools.document_constraints import DocumentInputLimitError
from app.tools.license_file_recognition import LocalPdfDocumentLoadError


router = APIRouter(prefix="/api/v1/business-license", tags=["business-license"])


class BusinessLicenseReviewReadRepository(Protocol):
    def list_business_license_reviews(
        self,
        *,
        business_name: str | None = None,
        credit_code: str | None = None,
        risk_level: str | None = None,
        review_status: str | None = None,
        needs_manual_review: bool | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        ...

    def get_business_license_snapshot(self, task_id: str) -> dict[str, Any] | None:
        ...

    def get_by_task_id(self, task_id: str) -> ReviewResult | None:
        ...

    def manual_review_business_license(
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

    def list_business_license_audit_events(self, task_id: str) -> list[dict[str, Any]]:
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


def get_review_service() -> ReviewService:
    return review_service


def get_review_read_repository() -> BusinessLicenseReviewReadRepository:
    return build_review_result_repository_from_env()


def get_srm_sql_client() -> SqlFetchClient:
    return MySqlFetchClient(mysql_settings_from_env("SRM_MYSQL"))


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


@router.post("/reviews/from-srm")
def create_business_license_review_from_srm(
    _current_user: dict[str, Any] = Depends(require_web_console_user),
    sql_client: SqlFetchClient = Depends(get_srm_sql_client),
    service: ReviewService = Depends(get_review_service),
) -> dict[str, Any]:
    try:
        task = fetch_one_business_license_source_task(sql_client)
    except BusinessLicenseSourceTaskError as error:
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
                "code": "BUSINESS_LICENSE_SOURCE_RECORD_NOT_FOUND",
                "message": "未找到可审核的营业执照来源记录",
            },
        )

    try:
        result = service.review(task.review_input, use_case_name="business_license")
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


@router.get("/reviews")
def list_business_license_reviews(
    business_name: str | None = Query(default=None),
    credit_code: str | None = Query(default=None),
    risk_level: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    needs_manual_review: bool | None = Query(default=None),
    created_from: str | None = Query(default=None),
    created_to: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _current_user: dict[str, Any] = Depends(require_web_console_user),
    repository: BusinessLicenseReviewReadRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    return repository.list_business_license_reviews(
        business_name=_blank_to_none(business_name),
        credit_code=_blank_to_none(credit_code),
        risk_level=_blank_to_none(risk_level),
        review_status=_blank_to_none(review_status),
        needs_manual_review=needs_manual_review,
        created_from=_blank_to_none(created_from),
        created_to=_blank_to_none(created_to),
        page=page,
        page_size=page_size,
    )


@router.get("/reviews/{task_id}")
def get_business_license_review_detail(
    task_id: str,
    _current_user: dict[str, Any] = Depends(require_web_console_user),
    repository: BusinessLicenseReviewReadRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    snapshot = repository.get_business_license_snapshot(task_id)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "BUSINESS_LICENSE_REVIEW_NOT_FOUND",
                "message": "未找到营业执照审核结果",
            },
        )

    result = repository.get_by_task_id(task_id)
    payload = result.model_dump(mode="json") if result is not None else None
    row = _detail_row(snapshot)
    return {
        **row,
        "source_url": snapshot.get("source_url"),
        "summary": snapshot.get("summary"),
        "business_address": snapshot.get("business_address"),
        "legal_person": snapshot.get("legal_person"),
        "valid_from": snapshot.get("valid_from"),
        "valid_to": snapshot.get("valid_to"),
        "issue_authority": snapshot.get("issue_authority"),
        "issue_date": snapshot.get("issue_date"),
        "rule_results": snapshot["rule_results"],
        "extracted_fields": snapshot["extracted_fields"],
        "normalized_fields": snapshot["normalized_fields"],
        "extraction_metadata": snapshot["extraction_metadata"],
        "source_evidence": snapshot["source_evidence"],
        "manual_review_reasons": (payload or {}).get("manual_review", {}).get("reasons", []),
        "manual_review": _manual_review(snapshot, payload),
        "audit_events": repository.list_business_license_audit_events(task_id),
        "payload": payload,
    }


@router.post("/reviews/{task_id}/manual-review")
def manual_review_business_license(
    task_id: str,
    request: ManualReviewRequest,
    current_user: dict[str, Any] = Depends(require_web_console_user),
    repository: BusinessLicenseReviewReadRepository = Depends(get_review_read_repository),
) -> dict[str, Any]:
    reviewed_at = datetime.now().astimezone()
    snapshot = repository.manual_review_business_license(
        task_id=task_id,
        decision=request.decision,
        comment=request.comment.strip(),
        reviewer_id=request.reviewer_id.strip(),
        reviewer_username=str(current_user.get("username") or ""),
        reviewed_at=reviewed_at,
    )
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "BUSINESS_LICENSE_REVIEW_NOT_FOUND",
                "message": "未找到营业执照审核结果",
            },
        )
    payload = repository.get_by_task_id(task_id)
    payload_dict = payload.model_dump(mode="json") if payload is not None else None
    row = _detail_row(snapshot)
    return {
        **row,
        "manual_review": _manual_review(snapshot, payload_dict),
        "audit_events": repository.list_business_license_audit_events(task_id),
        "payload": payload_dict,
    }


def _detail_row(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": snapshot["task_id"],
        "source_record_id": snapshot.get("source_record_id"),
        "source_attachment_ref_id": snapshot.get("source_attachment_ref_id"),
        "tenant": snapshot.get("tenant"),
        "document_type": snapshot.get("document_type"),
        "business_name": snapshot.get("business_name"),
        "credit_code": snapshot.get("credit_code"),
        "review_status": snapshot.get("review_status"),
        "review_status_label": _review_status_label(snapshot.get("review_status")),
        "risk_level": snapshot.get("risk_level"),
        "risk_level_label": _risk_level_label(snapshot.get("risk_level")),
        "needs_manual_review": bool(snapshot.get("needs_manual_review")),
        "manual_review_decision": snapshot.get("manual_review_decision"),
        "manual_review_comment": snapshot.get("manual_review_comment"),
        "reviewer_id": snapshot.get("manual_review_reviewer_id"),
        "reviewer_username": snapshot.get("manual_review_reviewer_username"),
        "reviewed_at": snapshot.get("manual_review_reviewed_at"),
        "created_at": snapshot.get("created_at"),
        "updated_at": snapshot.get("updated_at"),
    }


def _manual_review(snapshot: dict[str, Any], payload: dict[str, Any] | None) -> dict[str, Any]:
    payload_manual_review = dict((payload or {}).get("manual_review") or {})
    return {
        "status": snapshot.get("manual_review_status")
        or payload_manual_review.get("status")
        or "PENDING",
        "decision": snapshot.get("manual_review_decision")
        or payload_manual_review.get("action"),
        "comment": snapshot.get("manual_review_comment")
        or payload_manual_review.get("comment"),
        "reviewer_id": snapshot.get("manual_review_reviewer_id")
        or payload_manual_review.get("reviewer"),
        "reviewer_username": snapshot.get("manual_review_reviewer_username"),
        "reviewed_at": snapshot.get("manual_review_reviewed_at")
        or payload_manual_review.get("reviewed_at"),
        "reasons": payload_manual_review.get("reasons", []),
    }


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _review_status_label(status: str | None) -> str:
    return {
        "CREATED": "已创建",
        "RUNNING": "审核中",
        "REVIEWED": "已审核",
        "PENDING_MANUAL_REVIEW": "待人工复核",
        "MANUAL_REVIEWED": "人工已复核",
        "FAILED": "审核失败",
    }.get(status or "", status or "")


def _risk_level_label(risk_level: str | None) -> str:
    return {
        "NONE": "无风险",
        "LOW": "低风险",
        "MEDIUM": "中风险",
        "HIGH": "高风险",
    }.get(risk_level or "", risk_level or "")
