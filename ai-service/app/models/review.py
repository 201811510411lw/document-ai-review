from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SerializeAsAny


class RiskLevel(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


class ReviewStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    REVIEWED = "REVIEWED"
    PENDING_MANUAL_REVIEW = "PENDING_MANUAL_REVIEW"
    MANUAL_REVIEWED = "MANUAL_REVIEWED"
    FAILED = "FAILED"


class ManualReviewStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"


class ReviewDocumentInput(BaseModel):
    file_uri: str | None = None
    local_path: str | None = None
    file_path: str | None = None
    file_name: str | None = None
    mime_type: str | None = None
    file_type: str | None = None
    document_format: str | None = None
    stub_text: str | None = None


class ReviewInput(BaseModel):
    ocr_text: str | None = None
    file: ReviewDocumentInput | None = None
    document: ReviewDocumentInput | None = None
    supplier_name: str
    supplier_credit_code: str
    supplier_address: str | None = None
    declared_document_type: str | None = None
    source: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)


class ReviewInputContext(BaseModel):
    task_id: str
    input: ReviewInput
    skill_name: str
    skill_version: str
    ruleset_version: str


class RuleResult(BaseModel):
    rule_code: str
    rule_name: str
    passed: bool
    risk_level_on_failure: RiskLevel
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ManualReview(BaseModel):
    status: ManualReviewStatus
    reasons: list[str] = Field(default_factory=list)
    reviewer: str | None = None
    action: str | None = None
    comment: str | None = None
    reviewed_at: datetime | None = None


class AuditEvent(BaseModel):
    event_type: str
    message: str
    occurred_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    skill_name: str
    skill_version: str
    ruleset_version: str
    document_type: str
    status: ReviewStatus
    risk_level: RiskLevel
    needs_manual_review: bool
    rule_results: list[RuleResult] = Field(default_factory=list)
    summary: str
    manual_review: ManualReview
    audit_events: list[AuditEvent] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    skill_result: dict[str, Any] | SerializeAsAny[BaseModel]
