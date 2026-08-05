from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.auth import require_oa_token
from app.api.tobacco_license_consistency import (
    OaAutoReviewRequest,
    create_oa_auto_review,
    get_consistency_oa_result,
    manual_review_consistency_result,
    TobaccoManualReviewRequest,
)
from app.workflows.tobacco_license_consistency_review.decision import (
    oa_review_decision as _oa_decision,
)
from app.core.config import settings
from app.integrations.starrocks.tobacco_license_sources import TobaccoLicenseSourceFile
from app.models import (
    ManualReview,
    ManualReviewStatus,
    ReviewResult,
    ReviewStatus,
    RiskLevel,
    RuleResult,
)
from app.services.tobacco_license_files import (
    TobaccoLicenseStoredDocument,
    TobaccoLicenseStoredFile,
)


class ExistingResultRepository:
    def __init__(self, result):
        self.result = result
        self.reads = 0

    def get_by_task_id(self, task_id):
        self.reads += 1
        assert task_id == "tc-oa-614-584412"
        return self.result


class MustNotRun:
    def __getattr__(self, name):
        raise AssertionError(f"idempotent request unexpectedly used {name}")


class ManualReviewRepository:
    def __init__(self):
        self.call = None

    def manual_review_qc_review(self, **kwargs):
        self.call = kwargs
        return {"task_id": kwargs["task_id"], "manual_review_decision": kwargs["decision"]}

    def get_by_task_id(self, task_id):
        return _result().model_copy(
            update={
                "status": ReviewStatus.MANUAL_REVIEWED,
                "manual_review": ManualReview(
                    status=ManualReviewStatus.COMPLETED,
                    action=self.call["decision"],
                    reviewer=self.call["reviewer_id"],
                ),
            }
        )


class NewResultRepository:
    def __init__(self):
        self.saved = []
        self.lock = Lock()

    def get_by_task_id(self, task_id):
        return self.saved[-1] if self.saved and self.saved[-1].task_id == task_id else None

    def save(self, result):
        with self.lock:
            self.saved[:] = [item for item in self.saved if item.task_id != result.task_id]
            self.saved.append(result)

    def claim(self, result):
        with self.lock:
            if any(item.task_id == result.task_id for item in self.saved):
                return False
            self.saved.append(result)
            return True

    def release_claim(self, result):
        with self.lock:
            self.saved[:] = [
                item
                for item in self.saved
                if not (item.task_id == result.task_id and item.status == ReviewStatus.RUNNING)
            ]

    def complete_claim(self, claim, result):
        with self.lock:
            for index, existing in enumerate(self.saved):
                if existing.model_dump_json() == claim.model_dump_json():
                    self.saved[index] = result
                    return True
            return False


class FailingSaveRepository(NewResultRepository):
    def complete_claim(self, claim, result):
        raise RuntimeError("database unavailable")


class StoredDocumentsFileStore:
    def __init__(self, documents):
        self.documents = documents

    def store_source_files(self, source_files):
        return self.documents


class ChildReviewService:
    def review(self, review_input, use_case_name=None):
        fields = _business_fields() if use_case_name == "business_license" else _tobacco_fields()
        return _child_result(use_case_name, fields)


class ConflictingChildReviewService(ChildReviewService):
    def review(self, review_input, use_case_name=None):
        fields = _business_fields() if use_case_name == "business_license" else _tobacco_fields()
        if use_case_name == "tobacco_license":
            fields["license_no"] = review_input.source["record_id"]
        return _child_result(use_case_name, fields)


class MismatchingChildReviewService(ChildReviewService):
    def review(self, review_input, use_case_name=None):
        fields = _business_fields() if use_case_name == "business_license" else _tobacco_fields()
        if use_case_name == "tobacco_license":
            fields["subject_name"] = "另一主体"
        return _child_result(use_case_name, fields)


def test_oa_token_is_required_and_compared_against_dedicated_secret(monkeypatch):
    monkeypatch.setattr(settings, "oa_auto_review_token", "oa-secret")

    assert require_oa_token("oa-secret") == {"client": "oa"}
    with pytest.raises(HTTPException) as error:
        require_oa_token("wrong")
    assert error.value.status_code == 401
    assert error.value.detail["code"] == "OA_UNAUTHORIZED"


def test_empty_legacy_callback_url_is_ignored_but_non_empty_url_is_rejected():
    request = OaAutoReviewRequest(
        requestid=584412,
        store_code="00001",
        workflow_id=614,
        callback_url="",
    )

    assert request.callback_url is None
    with pytest.raises(ValueError):
        OaAutoReviewRequest(
            requestid=584412,
            store_code="00001",
            workflow_id=614,
            callback_url="https://oa.example/callback",
        )


def test_workflow_id_is_required_and_accepts_positive_custom_value():
    with pytest.raises(ValidationError):
        OaAutoReviewRequest(requestid=584412, store_code="00001")

    request = OaAutoReviewRequest(
        requestid=584412,
        store_code="00001",
        workflow_id=123,
    )
    assert request.workflow_id == 123

    with pytest.raises(ValidationError):
        OaAutoReviewRequest(
            requestid=584412,
            store_code="00001",
            workflow_id=0,
        )


def test_repeated_oa_request_returns_saved_result_without_reprocessing():
    repository = ExistingResultRepository(_result())

    response = create_oa_auto_review(
        OaAutoReviewRequest(requestid=584412, store_code="00001", workflow_id=614),
        _oa_client={"client": "oa"},
        sql_client=MustNotRun(),
        file_store=MustNotRun(),
        repository=repository,
        document_review_service=MustNotRun(),
    )

    assert response["data"]["decision"] == "pass"
    assert response["data"]["task_id"] == "tc-oa-614-584412"
    assert repository.reads == 1


def test_oa_auto_review_executes_current_project_review_chain(monkeypatch, tmp_path):
    source_files = [
        _source("business_license", 1001),
        _source("tobacco_license", 1002),
    ]
    documents = [_stored(tmp_path, source) for source in source_files]
    repository = NewResultRepository()

    def fetch_source_files(sql_client, requestid, workflow_id):
        assert requestid == 584412
        assert workflow_id == 123
        return source_files

    monkeypatch.setattr(
        "app.services.oa_tobacco_auto_review.fetch_tobacco_license_source_files_by_request",
        fetch_source_files,
    )
    monkeypatch.setattr(settings, "rpa_verification_tobacco_enabled", False)

    response = create_oa_auto_review(
        OaAutoReviewRequest(requestid=584412, store_code="00001", workflow_id=123),
        _oa_client={"client": "oa"},
        sql_client=object(),
        file_store=StoredDocumentsFileStore(documents),
        repository=repository,
        document_review_service=ChildReviewService(),
    )

    assert response["data"]["decision"] == "pass"
    assert response["data"]["task_id"] == "tc-oa-123-584412"
    assert repository.saved[-1].task_id == "tc-oa-123-584412"


def test_concurrent_repeated_request_executes_source_chain_once(monkeypatch, tmp_path):
    source_files = [_source("business_license", 1001), _source("tobacco_license", 1002)]
    documents = [_stored(tmp_path, source) for source in source_files]
    repository = NewResultRepository()
    calls = {"source": 0}
    source_lock = Lock()
    first_fetch_started = Event()
    duplicate_fetch_started = Event()
    release_fetch = Event()

    def fetch_once(sql_client, requestid, workflow_id):
        with source_lock:
            calls["source"] += 1
            call_number = calls["source"]
        if call_number == 1:
            first_fetch_started.set()
        else:
            duplicate_fetch_started.set()
        assert release_fetch.wait(timeout=5)
        return source_files

    monkeypatch.setattr(
        "app.services.oa_tobacco_auto_review.fetch_tobacco_license_source_files_by_request",
        fetch_once,
    )
    monkeypatch.setattr(settings, "rpa_verification_tobacco_enabled", False)

    def invoke():
        return create_oa_auto_review(
            OaAutoReviewRequest(requestid=584412, store_code="00001", workflow_id=614),
            _oa_client={"client": "oa"},
            sql_client=object(),
            file_store=StoredDocumentsFileStore(documents),
            repository=repository,
            document_review_service=ChildReviewService(),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(invoke)
        assert first_fetch_started.wait(timeout=5)
        second = pool.submit(invoke)
        duplicate_source_fetch = duplicate_fetch_started.wait(timeout=1)
        release_fetch.set()
        responses = [first.result(), second.result()]

    assert duplicate_source_fetch is False
    assert sorted(item["data"]["decision"] for item in responses) == ["exception", "pass"]
    in_progress = next(item for item in responses if item["data"]["decision"] == "exception")
    assert in_progress["data"]["error"]["code"] == "REVIEW_IN_PROGRESS"
    assert calls["source"] == 1


def test_conflicting_candidates_are_persisted_for_manual_review(monkeypatch, tmp_path):
    source_files = [
        _source("business_license", 1001),
        _source("tobacco_license", 1002),
        _source("tobacco_license", 1003),
    ]
    documents = [_stored(tmp_path, source) for source in source_files]
    repository = NewResultRepository()
    monkeypatch.setattr(
        "app.services.oa_tobacco_auto_review.fetch_tobacco_license_source_files_by_request",
        lambda sql_client, requestid, workflow_id: source_files,
    )
    monkeypatch.setattr(settings, "rpa_verification_tobacco_enabled", False)

    response = create_oa_auto_review(
        OaAutoReviewRequest(requestid=584412, store_code="00001", workflow_id=614),
        _oa_client={"client": "oa"},
        sql_client=object(),
        file_store=StoredDocumentsFileStore(documents),
        repository=repository,
        document_review_service=ConflictingChildReviewService(),
    )

    assert response["data"]["decision"] == "manual_review"
    assert repository.saved[-1].needs_manual_review is True


def test_result_save_failure_returns_exception_not_in_memory_pass(monkeypatch, tmp_path):
    source_files = [_source("business_license", 1001), _source("tobacco_license", 1002)]
    documents = [_stored(tmp_path, source) for source in source_files]
    monkeypatch.setattr(
        "app.services.oa_tobacco_auto_review.fetch_tobacco_license_source_files_by_request",
        lambda sql_client, requestid, workflow_id: source_files,
    )
    monkeypatch.setattr(settings, "rpa_verification_tobacco_enabled", False)

    response = create_oa_auto_review(
        OaAutoReviewRequest(requestid=584412, store_code="00001", workflow_id=614),
        _oa_client={"client": "oa"},
        sql_client=object(),
        file_store=StoredDocumentsFileStore(documents),
        repository=FailingSaveRepository(),
        document_review_service=ChildReviewService(),
    )

    assert response["data"]["decision"] == "exception"
    assert response["data"]["error"]["code"] == "AUTO_REVIEW_FAILED"
    assert "database unavailable" not in response["data"]["error"]["message"]


def test_deterministic_reject_still_runs_one_rpa_verification(monkeypatch, tmp_path):
    source_files = [_source("business_license", 1001), _source("tobacco_license", 1002)]
    documents = [_stored(tmp_path, source) for source in source_files]
    repository = NewResultRepository()
    rpa_calls = []
    monkeypatch.setattr(
        "app.services.oa_tobacco_auto_review.fetch_tobacco_license_source_files_by_request",
        lambda sql_client, requestid, workflow_id: source_files,
    )
    monkeypatch.setattr(
        "app.services.oa_tobacco_auto_review.execute_tobacco_rpa_verification",
        lambda **kwargs: (
            rpa_calls.append(kwargs["certificate_no"])
            or {"status": "AUTHENTIC"}
        ),
    )

    response = create_oa_auto_review(
        OaAutoReviewRequest(requestid=584412, store_code="00001", workflow_id=614),
        _oa_client={"client": "oa"},
        sql_client=object(),
        file_store=StoredDocumentsFileStore(documents),
        repository=repository,
        document_review_service=MismatchingChildReviewService(),
    )

    assert response["data"]["decision"] == "reject"
    assert rpa_calls == ["510100000001"]


def test_rpa_is_not_repeated_when_final_persistence_fails(monkeypatch, tmp_path):
    source_files = [_source("business_license", 1001), _source("tobacco_license", 1002)]
    documents = [_stored(tmp_path, source) for source in source_files]
    repository = FailingSaveRepository()
    rpa_calls = []
    monkeypatch.setattr(
        "app.services.oa_tobacco_auto_review.fetch_tobacco_license_source_files_by_request",
        lambda sql_client, requestid, workflow_id: source_files,
    )
    monkeypatch.setattr(
        "app.services.oa_tobacco_auto_review.execute_tobacco_rpa_verification",
        lambda **kwargs: rpa_calls.append(kwargs["task_id"]) or {"status": "AUTHENTIC"},
    )

    def invoke():
        return create_oa_auto_review(
            OaAutoReviewRequest(requestid=584412, store_code="00001", workflow_id=614),
            _oa_client={"client": "oa"},
            sql_client=object(),
            file_store=StoredDocumentsFileStore(documents),
            repository=repository,
            document_review_service=ChildReviewService(),
        )

    first = invoke()
    second = invoke()

    assert first["data"]["error"]["code"] == "RESULT_STORE_UNAVAILABLE"
    assert first["data"]["error"]["retryable"] is False
    assert second["data"]["error"]["code"] == "REVIEW_IN_PROGRESS"
    assert rpa_calls == ["tc-oa-614-584412"]


def test_incomplete_evidence_is_manual_review_not_reject():
    rule = _rule(
        "TOBACCO_LICENSE_EVIDENCE_FOR_CONSISTENCY",
        details={"missing_evidence_fields": ["license_no_evidence"]},
    )

    assert _oa_decision(_result(rule)) == "manual_review"


def test_complete_deterministic_mismatch_is_rejected():
    rule = _rule(
        "BUSINESS_TOBACCO_SUBJECT_NAME_MATCH",
        details={"expected": "甲公司", "actual": "乙公司", "difference": "value_mismatch"},
    )

    assert _oa_decision(_result(rule)) == "reject"


def test_rpa_technical_error_is_exception():
    result = _result().model_copy(
        update={"skill_result": {"rpa_verification": {"status": "ERROR"}}}
    )

    assert _oa_decision(result) == "exception"


def test_request_more_info_remains_manual_review_even_without_failed_rules():
    result = _result().model_copy(
        update={
            "status": ReviewStatus.PENDING_MANUAL_REVIEW,
            "needs_manual_review": True,
            "manual_review": ManualReview(
                status=ManualReviewStatus.COMPLETED,
                action="request_more_info",
            ),
        }
    )

    assert _oa_decision(result) == "manual_review"


def test_oa_polling_is_consistent_after_manual_approval():
    result = _result(
        _rule(
            "BUSINESS_TOBACCO_SUBJECT_NAME_MATCH",
            details={"expected": "甲公司", "actual": "乙公司"},
        )
    ).model_copy(
        update={
            "status": ReviewStatus.MANUAL_REVIEWED,
            "manual_review": ManualReview(
                status=ManualReviewStatus.COMPLETED,
                action="approved",
            ),
        }
    )
    repository = ExistingResultRepository(result)

    response = get_consistency_oa_result(
        result.task_id,
        _oa_client={"client": "oa"},
        repository=repository,
    )

    callback = response["data"]["callback"]
    assert callback["decision"] == "pass"
    assert callback["review_status"] == "通过"
    assert callback["needs_manual_review"] is False


def test_oa_polling_redacts_internal_rpa_error_text():
    result = _result().model_copy(
        update={
            "skill_result": {
                "rpa_verification": {
                    "status": "ERROR",
                    "error_message": "POST https://internal-rpa.local failed",
                    "raw_yindao_response": {"internal": "secret"},
                }
            }
        }
    )
    repository = ExistingResultRepository(result)

    response = get_consistency_oa_result(
        result.task_id,
        _oa_client={"client": "oa"},
        repository=repository,
    )

    rpa = response["data"]["callback"]["rpa_verification"]
    assert rpa == {
        "status": "ERROR",
        "error_message": "烟草证官网验真未可靠完成",
    }


def test_oa_polling_never_passes_a_running_claim():
    result = _result().model_copy(update={"status": ReviewStatus.RUNNING})
    repository = ExistingResultRepository(result)

    response = get_consistency_oa_result(
        result.task_id,
        _oa_client={"client": "oa"},
        repository=repository,
    )

    callback = response["data"]["callback"]
    assert callback["decision"] == "exception"
    assert callback["review_status"] == "异常"
    assert callback["needs_manual_review"] is True
    assert callback["error"] == {
        "code": "REVIEW_IN_PROGRESS",
        "message": "自动审核正在执行，请稍后轮询",
        "retryable": True,
    }


def test_manual_review_is_persisted_through_repository():
    repository = ManualReviewRepository()

    response = manual_review_consistency_result(
        "tc-oa-614-584412",
        TobaccoManualReviewRequest(decision="APPROVE", comment="证据已人工确认"),
        _current_user={"username": "reviewer", "external_id": "wx-reviewer"},
        repository=repository,
    )

    assert repository.call["decision"] == "approved"
    assert repository.call["reviewer_id"] == "wx-reviewer"
    assert response["payload"]["manual_review"]["action"] == "approved"


def _rule(code, *, details):
    return RuleResult(
        rule_code=code,
        rule_name="测试规则",
        passed=False,
        risk_level_on_failure=RiskLevel.MEDIUM,
        message="未通过",
        details=details,
    )


def _result(*rules):
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    return ReviewResult(
        task_id="tc-oa-614-584412",
        use_case_name="tobacco_license_consistency_review",
        use_case_version="v1",
        skill_name="tobacco_license_consistency_review",
        skill_version="v1",
        ruleset_version="v1",
        document_type="business_tobacco_consistency",
        status=(ReviewStatus.PENDING_MANUAL_REVIEW if rules else ReviewStatus.REVIEWED),
        risk_level=(RiskLevel.MEDIUM if rules else RiskLevel.NONE),
        needs_manual_review=bool(rules),
        rule_results=list(rules),
        summary="审核完成",
        manual_review=ManualReview(
            status=(ManualReviewStatus.PENDING if rules else ManualReviewStatus.NOT_REQUIRED)
        ),
        created_at=now,
        updated_at=now,
        skill_result={},
    )


def _child_result(document_type, fields):
    return _result().model_copy(
        update={
            "task_id": f"child-{document_type}",
            "use_case_name": document_type,
            "skill_name": document_type,
            "document_type": document_type,
            "skill_result": {"normalized_fields": fields},
        }
    )


def _business_fields():
    return {
        "document_type": "business_license",
        "subject_name": "示例商行",
        "business_address": "成都市示例路1号",
        "legal_person": "张三",
        "subject_name_evidence": "名称：示例商行",
        "business_address_evidence": "地址：成都市示例路1号",
        "legal_person_evidence": "经营者：张三",
    }


def _tobacco_fields():
    return {
        "document_type": "tobacco_license",
        "subject_name": "示例商行",
        "business_address": "成都市示例路1号",
        "legal_person": "张三",
        "license_no": "510100000001",
        "valid_to": "2099-12-31",
        "subject_name_evidence": "企业名称：示例商行",
        "business_address_evidence": "经营场所：成都市示例路1号",
        "legal_person_evidence": "负责人：张三",
        "license_no_evidence": "许可证号：510100000001",
        "valid_to_evidence": "有效期至：2099-12-31",
    }


def _source(role, docid):
    return TobaccoLicenseSourceFile(
        requestid=584412,
        workflow_id=614,
        store_code="00001",
        store_name="示例门店",
        document_role=role,
        docid=docid,
        imagefile_id=docid + 1,
        file_real_path=f"/nas/{role}.jpg",
    )


def _stored(tmp_path, source):
    path = tmp_path / f"{source.document_role}.jpg"
    path.write_bytes(b"image")
    return TobaccoLicenseStoredDocument(
        source=source,
        output_dir=str(tmp_path),
        files=[
            TobaccoLicenseStoredFile(
                file_name=path.name,
                relative_path=path.name,
                local_path=str(path),
                content_type="image/jpeg",
                file_size=path.stat().st_size,
            )
        ],
    )
