from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.auth import require_oa_token
from app.api.tobacco_license_consistency import (
    OaAutoReviewRequest,
    _oa_response,
    _run_oa_auto_review_and_callback,
    create_oa_auto_review,
    get_consistency_oa_result,
    manual_review_consistency_result,
    retry_oa_review_callback,
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
from app.services.oa_auto_review_callback import OaAutoReviewCallbackDelivery
from app.services.oa_tobacco_auto_review import (
    OaAutoReviewCommand,
    OaAutoReviewError,
    OaAutoReviewOutcome,
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
                    comment=self.call["comment"],
                    reviewer=self.call["reviewer_id"],
                ),
            }
        )


class CapturingCallbackClient:
    def __init__(self):
        self.payloads = []

    def send(self, payload):
        self.payloads.append(payload)
        return OaAutoReviewCallbackDelivery(
            target="http://oa.example.test/api/bicallback/result",
            attempt_count=1,
            http_status=200,
            response_body={"code": 0, "message": "received"},
            business_accepted=True,
        )


class FailingCallbackClient:
    def send(self, payload):
        raise RuntimeError("callback unavailable")


class ClaimLostReviewService:
    def review(self, command):
        return OaAutoReviewOutcome(
            task_id="tc-oa-614-584412",
            error=OaAutoReviewError(
                code="REVIEW_CLAIM_LOST",
                message="自动审核任务占位已失效，结果未写入",
                retryable=False,
            ),
        )

    def update_callback_state(self, *args, **kwargs):
        raise AssertionError("claim-lost attempt unexpectedly updated callback state")


def test_claim_lost_background_attempt_does_not_send_callback():
    _run_oa_auto_review_and_callback(
        command=OaAutoReviewCommand(
            requestid=584412,
            store_code="00001",
            workflow_id=614,
        ),
        review_service=ClaimLostReviewService(),
        callback_client=MustNotRun(),
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

    def advance_claim(self, claim, result):
        return self.complete_claim(claim, result)

    def complete_claim(self, claim, result):
        with self.lock:
            for index, existing in enumerate(self.saved):
                if existing.model_dump_json() == claim.model_dump_json():
                    self.saved[index] = result
                    return True
            return False


def test_timeout_callback_can_be_retried_without_changing_review_decision():
    result = _result().model_copy(update={
        "status": ReviewStatus.FAILED,
        "risk_level": RiskLevel.HIGH,
        "needs_manual_review": True,
        "skill_result": {
            "oa_claim": {
                "workflow_id": 614,
                "requestid": 584412,
                "store_code": "0001",
            },
            "oa_error": {
                "code": "AUTO_REVIEW_TIMEOUT",
                "message": "自动审核超过处理时限",
                "retryable": True,
            },
        },
    })
    repository = NewResultRepository()
    repository.saved.append(result)
    callback_client = CapturingCallbackClient()

    response = retry_oa_review_callback(
        result.task_id,
        _current_user={"username": "reviewer"},
        repository=repository,
        callback_client=callback_client,
    )

    callback = callback_client.payloads[0]
    assert callback.workflow_id == 614
    assert callback.requestid == 584412
    assert callback.result["data"]["decision"] == "exception"
    assert callback.result["data"]["error"]["code"] == "AUTO_REVIEW_TIMEOUT"
    assert callback.result["data"]["error"]["retryable"] is True
    assert response["status"] == "SENT"
    assert response["task_id"] == result.task_id
    assert repository.saved[-1].skill_result["oa_callback"]["status"] == "SENT"
    audit = repository.saved[-1].skill_result["oa_callback_history"][-1]
    assert audit["trigger"] == "manual_retry"
    assert audit["target"] == "http://oa.example.test/api/bicallback/result"
    assert audit["request_payload"]["requestid"] == 584412
    assert audit["http_status"] == 200
    assert audit["response_body"] == {"code": 0, "message": "received"}
    assert audit["business_accepted"] is True


def test_manual_review_callback_uses_three_state_oa_transport_and_keeps_reasons():
    rule = _rule(
        "TOBACCO_LICENSE_EVIDENCE_FOR_CONSISTENCY",
        details={"missing_evidence_fields": ["license_no_evidence"]},
    )
    result = _result(rule).model_copy(update={
        "skill_result": {
            "oa_claim": {
                "workflow_id": 614,
                "requestid": 584412,
                "store_code": "0001",
            },
        },
    })
    repository = NewResultRepository()
    repository.saved.append(result)
    callback_client = CapturingCallbackClient()

    response = retry_oa_review_callback(
        result.task_id,
        _current_user={"username": "reviewer"},
        repository=repository,
        callback_client=callback_client,
    )

    assert response["status"] == "SENT"
    data = callback_client.payloads[0].result["data"]
    assert data["decision"] == "exception"
    assert data["error"] == {
        "code": "REVIEW_REQUIRES_MANUAL_REVIEW",
        "message": "未通过",
        "retryable": False,
    }
    assert data["manual_review_reason_text"] == "未通过"
    assert data["manual_review_reasons"][0]["suggestion"]
    assert data["rule_results"][0]["rule_code"] == rule.rule_code
    assert data["rule_results"][0]["passed"] is False
    assert data["rule_results"][0]["suggestion"]
    assert repository.saved[-1].status == ReviewStatus.PENDING_MANUAL_REVIEW
    assert repository.saved[-1].needs_manual_review is True


def test_manual_callback_retry_rejects_non_oa_task():
    repository = NewResultRepository()
    repository.saved.append(_result())

    with pytest.raises(HTTPException) as error:
        retry_oa_review_callback(
            "tc-oa-614-584412",
            _current_user={"username": "reviewer"},
            repository=repository,
            callback_client=CapturingCallbackClient(),
        )

    assert error.value.status_code == 422
    assert error.value.detail["code"] == "OA_IDENTITY_MISSING"


def test_manual_callback_retry_persists_delivery_failure():
    result = _result().model_copy(update={
        "status": ReviewStatus.FAILED,
        "skill_result": {
            "oa_claim": {
                "workflow_id": 614,
                "requestid": 584412,
                "store_code": "0001",
            }
        },
    })
    repository = NewResultRepository()
    repository.saved.append(result)

    with pytest.raises(HTTPException) as error:
        retry_oa_review_callback(
            result.task_id,
            _current_user={"username": "reviewer"},
            repository=repository,
            callback_client=FailingCallbackClient(),
        )

    assert error.value.status_code == 502
    assert error.value.detail["code"] == "OA_CALLBACK_FAILED"
    assert repository.saved[-1].skill_result["oa_callback"]["status"] == "FAILED"


class FailingSaveRepository(NewResultRepository):
    def advance_claim(self, claim, result):
        return NewResultRepository.complete_claim(self, claim, result)

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


class RejectingChildReviewService(ChildReviewService):
    def review(self, review_input, use_case_name=None):
        fields = (
            _business_fields()
            if use_case_name == "business_license"
            else _tobacco_fields()
        )
        if use_case_name == "tobacco_license":
            fields.update(
                {
                    "subject_name": "另一主体",
                    "business_address": "成都市另一地址",
                    "legal_person": "李四",
                }
            )
        return _child_result(use_case_name, fields)


class UnreliableRejectingChildReviewService(RejectingChildReviewService):
    def review(self, review_input, use_case_name=None):
        result = super().review(review_input, use_case_name)
        fields = dict(result.skill_result["normalized_fields"])
        for field in (
            "subject_name_evidence",
            "business_address_evidence",
            "legal_person_evidence",
            "license_no_evidence",
            "valid_to_evidence",
        ):
            fields.pop(field, None)
        updates = {"skill_result": {"normalized_fields": fields}}
        if use_case_name == "business_license":
            updates.update(
                {
                    "status": ReviewStatus.PENDING_MANUAL_REVIEW,
                    "needs_manual_review": True,
                    "manual_review": ManualReview(status=ManualReviewStatus.PENDING),
                }
            )
        return result.model_copy(update=updates)


class EmptyFieldsChildReviewService(ChildReviewService):
    def review(self, review_input, use_case_name=None):
        return _child_result(use_case_name, {})


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
    assert response["data"]["mismatch_count"] == 0
    assert response["data"]["field_differences"] == []
    rules_by_code = {
        rule["rule_code"]: rule for rule in response["data"]["rule_results"]
    }
    for rule_code, field in (
        ("BUSINESS_TOBACCO_SUBJECT_NAME_MATCH", "subject_name"),
        ("BUSINESS_TOBACCO_ADDRESS_MATCH", "business_address"),
        ("BUSINESS_TOBACCO_PERSON_MATCH", "legal_person"),
    ):
        rule = rules_by_code[rule_code]
        assert rule["passed"] is True
        assert rule["message"].endswith("通过")
        assert rule["details"] == {
            "field": field,
            "expected": _business_fields()[field],
            "actual": _tobacco_fields()[field],
            "difference": None,
            "evidence": {
                "expected_source": "business_license",
                "actual_source": "tobacco_license",
            },
        }
    validity_rule = rules_by_code["BUSINESS_TOBACCO_TOBACCO_VALIDITY"]
    assert validity_rule["passed"] is True
    assert validity_rule["message"] == "烟草证在有效期内"
    assert validity_rule["details"]["actual"] == "2099-12-31"
    assert validity_rule["details"]["difference"] is None
    assert validity_rule["details"]["evidence"] == {
        "actual_source": "tobacco_license"
    }
    assert repository.saved[-1].task_id == "tc-oa-123-584412"


def test_concurrent_repeated_request_executes_source_chain_once(monkeypatch, tmp_path):
    source_files = [
        _source("business_license", 1001),
        _source("tobacco_license", 1002),
    ]
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
    assert response["data"]["needs_manual_review"] is True
    assert response["data"]["mismatch_count"] >= 3
    assert response["data"]["manual_review_reasons"]
    assert "reject_reasons" not in response["data"]
    assert repository.saved[-1].needs_manual_review is True


def test_empty_child_fields_complete_parent_as_manual_review(monkeypatch, tmp_path):
    source_files = [
        _source("business_license", 1001),
        _source("tobacco_license", 1002),
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
        document_review_service=EmptyFieldsChildReviewService(),
    )

    assert response["data"]["decision"] == "manual_review"
    assert response["data"]["needs_manual_review"] is True
    assert response["data"]["manual_review_reasons"]
    assert "reject_reasons" not in response["data"]
    assert response["data"]["mismatch_count"] >= 3
    assert repository.saved[-1].status == ReviewStatus.PENDING_MANUAL_REVIEW
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
    assert response["data"]["error"]["code"] == "RESULT_STORE_UNAVAILABLE"
    assert response["data"]["error"]["retryable"] is True
    assert "database unavailable" not in response["data"]["error"]["message"]


def test_small_field_mismatch_passes_to_next_node_and_runs_rpa(monkeypatch, tmp_path):
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

    assert response["data"]["decision"] == "pass"
    assert response["data"]["mismatch_count"] == 1
    assert response["data"]["next_node_review_required"] is True
    assert response["data"]["field_differences"] == [
        {
            "field": "subject_name",
            "field_label": "主体名称",
            "expected": "示例商行",
            "actual": "另一主体",
            "difference": "value_mismatch",
            "rule_code": "BUSINESS_TOBACCO_SUBJECT_NAME_MATCH",
            "rule_name": "主体名称一致",
            "message": "营业执照主体名称与烟草证主体名称不一致",
        }
    ]
    assert rpa_calls == ["510100000001"]


def test_rejected_consistency_result_skips_rpa_and_preserves_reject_reasons(
    monkeypatch,
    tmp_path,
):
    source_files = [
        _source("business_license", 1001),
        _source("tobacco_license", 1002),
    ]
    documents = [_stored(tmp_path, source) for source in source_files]
    repository = NewResultRepository()
    monkeypatch.setattr(
        "app.services.oa_tobacco_auto_review.fetch_tobacco_license_source_files_by_request",
        lambda sql_client, requestid, workflow_id: source_files,
    )

    def unexpected_rpa(**kwargs):
        raise AssertionError("business rejection must short-circuit RPA verification")

    monkeypatch.setattr(
        "app.services.oa_tobacco_auto_review.execute_tobacco_rpa_verification",
        unexpected_rpa,
    )

    response = create_oa_auto_review(
        OaAutoReviewRequest(requestid=584412, store_code="00001", workflow_id=614),
        _oa_client={"client": "oa"},
        sql_client=object(),
        file_store=StoredDocumentsFileStore(documents),
        repository=repository,
        document_review_service=RejectingChildReviewService(),
    )

    assert response["data"]["decision"] == "reject"
    assert response["data"]["summary"] == "一致性核对未通过，共 3 项问题"
    assert response["data"]["mismatch_count"] == 3
    assert [reason["rule_code"] for reason in response["data"]["reject_reasons"]] == [
        "BUSINESS_TOBACCO_SUBJECT_NAME_MATCH",
        "BUSINESS_TOBACCO_ADDRESS_MATCH",
        "BUSINESS_TOBACCO_PERSON_MATCH",
    ]


def test_unreliable_child_reviews_do_not_automatically_reject_oa_request(
    monkeypatch,
    tmp_path,
):
    source_files = [
        _source("business_license", 1001),
        _source("tobacco_license", 1002),
    ]
    documents = [_stored(tmp_path, source) for source in source_files]
    repository = NewResultRepository()
    monkeypatch.setattr(
        "app.services.oa_tobacco_auto_review.fetch_tobacco_license_source_files_by_request",
        lambda sql_client, requestid, workflow_id: source_files,
    )

    response = create_oa_auto_review(
        OaAutoReviewRequest(requestid=584412, store_code="00001", workflow_id=614),
        _oa_client={"client": "oa"},
        sql_client=object(),
        file_store=StoredDocumentsFileStore(documents),
        repository=repository,
        document_review_service=UnreliableRejectingChildReviewService(),
    )

    assert response["data"]["decision"] == "manual_review"
    assert response["data"]["needs_manual_review"] is True
    assert response["data"]["mismatch_count"] == 3
    assert "reject_reasons" not in response["data"]
    assert [
        reason["rule_code"] for reason in response["data"]["manual_review_reasons"]
    ] == [
        "BUSINESS_LICENSE_CHILD_REVIEW_READY",
        "BUSINESS_LICENSE_EVIDENCE_FOR_CONSISTENCY",
        "TOBACCO_LICENSE_EVIDENCE_FOR_CONSISTENCY",
    ]
    assert response["data"]["manual_review_reason_text"] == (
        "营业执照子审核未形成可靠自动结论；"
        "营业执照关键字段证据完整不足；"
        "烟草证关键字段证据完整不足"
    )
    assert all(
        reason["suggestion"]
        for reason in response["data"]["manual_review_reasons"]
    )


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


def test_incomplete_evidence_requires_manual_review():
    rule = _rule(
        "TOBACCO_LICENSE_EVIDENCE_FOR_CONSISTENCY",
        details={"missing_evidence_fields": ["license_no_evidence"]},
    )

    assert _oa_decision(_result(rule)) == "manual_review"


def test_one_field_mismatch_passes_to_next_node():
    rule = _rule(
        "BUSINESS_TOBACCO_SUBJECT_NAME_MATCH",
        details={"expected": "甲公司", "actual": "乙公司", "difference": "value_mismatch"},
    )

    assert _oa_decision(_result(rule)) == "pass"


def test_two_field_mismatches_pass_with_structured_differences():
    result = _result(
        _rule(
            "BUSINESS_TOBACCO_SUBJECT_NAME_MATCH",
            details={
                "field": "subject_name",
                "expected": "甲公司",
                "actual": "乙公司",
                "difference": "value_mismatch",
            },
        ),
        _rule(
            "BUSINESS_TOBACCO_PERSON_MATCH",
            details={
                "field": "legal_person",
                "expected": "张三",
                "actual": "李四",
                "difference": "value_mismatch",
            },
        ),
    )

    response = _oa_response(result)["data"]

    assert response["decision"] == "pass"
    assert response["mismatch_count"] == 2
    assert response["mismatch_rejection_threshold"] == 3
    assert response["next_node_review_required"] is True
    assert [item["field"] for item in response["field_differences"]] == [
        "subject_name",
        "legal_person",
    ]


def test_expired_tobacco_license_is_rejected_with_detailed_reasons():
    result = _result(
        _rule(
            "BUSINESS_TOBACCO_SUBJECT_NAME_MATCH",
            details={
                "field": "subject_name",
                "expected": "甲便利店有限公司",
                "actual": "乙便利店有限公司",
                "difference": "value_mismatch",
            },
        ),
        RuleResult(
            rule_code="BUSINESS_TOBACCO_TOBACCO_VALIDITY",
            rule_name="烟草证有效期",
            passed=False,
            risk_level_on_failure=RiskLevel.HIGH,
            message="烟草证已过期",
            details={
                "field": "valid_to",
                "expected": "not_expired",
                "actual": "2026-06-30",
                "difference": "expired",
                "days_until_expiry": -63,
                "evidence": {"actual_source": "tobacco_license"},
            },
        ),
    )

    response = _oa_response(result)["data"]

    assert response["decision"] == "reject"
    assert response["summary"] == "一致性核对未通过，共 2 项问题"
    assert response["mismatch_count"] == 2
    assert response["next_node_review_required"] is False
    assert response["needs_manual_review"] is False
    assert [reason["rule_code"] for reason in response["reject_reasons"]] == [
        "BUSINESS_TOBACCO_SUBJECT_NAME_MATCH",
        "BUSINESS_TOBACCO_TOBACCO_VALIDITY",
    ]
    assert response["reject_reasons"][0]["details"]["expected"] == "甲便利店有限公司"
    assert response["reject_reasons"][0]["details"]["actual"] == "乙便利店有限公司"
    assert response["reject_reasons"][1]["details"]["actual"] == "2026-06-30"
    assert response["reject_reasons"][1]["details"]["difference"] == "expired"


def test_expired_tobacco_license_remains_hard_reject_when_other_evidence_is_missing():
    result = _result(
        _rule(
            "TOBACCO_LICENSE_EVIDENCE_FOR_CONSISTENCY",
            details={"missing_evidence_fields": ["subject_name_evidence"]},
        ),
        RuleResult(
            rule_code="BUSINESS_TOBACCO_TOBACCO_VALIDITY",
            rule_name="烟草证有效期",
            passed=False,
            risk_level_on_failure=RiskLevel.HIGH,
            message="烟草证已过期",
            details={
                "field": "valid_to",
                "actual": "2026-06-30",
                "difference": "expired",
                "evidence": {"actual_source": "tobacco_license"},
            },
        ),
    )

    assert _oa_decision(result) == "reject"


def test_three_field_mismatches_are_rejected():
    result = _result(
        _rule(
            "BUSINESS_TOBACCO_SUBJECT_NAME_MATCH",
            details={
                "field": "subject_name",
                "expected": "甲公司",
                "actual": "乙公司",
                "difference": "value_mismatch",
            },
        ),
        _rule(
            "BUSINESS_TOBACCO_ADDRESS_MATCH",
            details={
                "field": "business_address",
                "expected": "甲地址",
                "actual": "乙地址",
                "difference": "value_mismatch",
            },
        ),
        _rule(
            "BUSINESS_TOBACCO_PERSON_MATCH",
            details={
                "field": "legal_person",
                "expected": "张三",
                "actual": "李四",
                "difference": "value_mismatch",
            },
        ),
    )

    response = _oa_response(result)["data"]

    assert response["decision"] == "reject"
    assert response["mismatch_count"] == 3
    assert response["mismatch_rejection_threshold"] == 3
    assert response["next_node_review_required"] is False
    assert len(response["field_differences"]) == 3


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
    assert callback["mismatch_count"] == 1
    assert callback["next_node_review_required"] is False


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
    callback_client = CapturingCallbackClient()

    response = manual_review_consistency_result(
        "tc-oa-614-584412",
        TobaccoManualReviewRequest(decision="APPROVE", comment="证据已人工确认"),
        _current_user={"username": "reviewer", "external_id": "wx-reviewer"},
        repository=repository,
        callback_client=callback_client,
    )

    assert repository.call["decision"] == "approved"
    assert repository.call["reviewer_id"] == "wx-reviewer"
    assert response["payload"]["manual_review"]["action"] == "approved"
    assert callback_client.payloads == []


def test_manual_review_of_oa_timeout_callbacks_final_decision():
    repository = ManualReviewRepository()
    callback_client = CapturingCallbackClient()
    result = _result().model_copy(update={
        "status": ReviewStatus.FAILED,
        "risk_level": RiskLevel.HIGH,
        "needs_manual_review": True,
        "skill_result": {
            "oa_claim": {
                "workflow_id": 614,
                "requestid": 584412,
                "store_code": "0001",
            }
        },
    })

    repository.get_by_task_id = lambda task_id: result.model_copy(update={
        "status": ReviewStatus.MANUAL_REVIEWED,
        "needs_manual_review": False,
        "manual_review": ManualReview(
            status=ManualReviewStatus.COMPLETED,
            action=repository.call["decision"] if repository.call else "approved",
            comment=repository.call["comment"] if repository.call else "",
        ),
    })
    response = manual_review_consistency_result(
        result.task_id,
        TobaccoManualReviewRequest(decision="REJECT", comment="确认不合规"),
        _current_user={"username": "reviewer", "external_id": "wx-reviewer"},
        repository=repository,
        callback_client=callback_client,
    )

    assert response["oa_callback"]["status"] == "SENT"
    assert response["oa_callback"]["error"] is None
    assert callback_client.payloads[0].workflow_id == 614
    assert callback_client.payloads[0].requestid == 584412
    callback_data = callback_client.payloads[0].result["data"]
    assert callback_data["decision"] == "reject"
    assert callback_data["summary"] == "人工复核驳回：确认不合规"
    assert callback_data["reject_reason_text"] == "确认不合规"
    assert callback_data["rule_results"] == []
    assert callback_data["reject_reasons"] == [
        {
            "rule_code": "MANUAL_REVIEW_REJECTED",
            "rule_name": "人工复核结论",
            "message": "确认不合规",
            "suggestion": "请根据人工复核意见处理后重新提交",
        }
    ]


def test_manual_review_requires_comment_for_reject_and_more_info():
    for decision in ("REJECT", "REQUEST_MORE_INFO"):
        with pytest.raises(ValidationError):
            TobaccoManualReviewRequest(decision=decision, comment="  ")


def test_request_more_info_uses_three_state_callback_with_reason():
    repository = ManualReviewRepository()
    callback_client = CapturingCallbackClient()
    result = _result().model_copy(update={
        "status": ReviewStatus.FAILED,
        "risk_level": RiskLevel.HIGH,
        "needs_manual_review": True,
        "skill_result": {
            "oa_claim": {
                "workflow_id": 614,
                "requestid": 584412,
                "store_code": "0001",
            }
        },
    })
    repository.get_by_task_id = lambda task_id: result.model_copy(update={
        "status": ReviewStatus.PENDING_MANUAL_REVIEW,
        "needs_manual_review": True,
        "manual_review": ManualReview(
            status=ManualReviewStatus.COMPLETED,
            action="request_more_info",
            comment="请补充清晰的烟草证原件",
        ),
    })

    manual_review_consistency_result(
        result.task_id,
        TobaccoManualReviewRequest(
            decision="REQUEST_MORE_INFO",
            comment="请补充清晰的烟草证原件",
        ),
        _current_user={"username": "reviewer"},
        repository=repository,
        callback_client=callback_client,
    )

    data = callback_client.payloads[0].result["data"]
    assert data["decision"] == "exception"
    assert data["summary"] == "系统无法自动完成核对，需人工处理"
    assert data["needs_manual_review"] is True
    assert data["manual_review_reason_text"] == "请补充清晰的烟草证原件"
    assert data["manual_review_reasons"][-1]["suggestion"]
    assert data["error"] == {
        "code": "REVIEW_REQUIRES_MANUAL_REVIEW",
        "message": "请补充清晰的烟草证原件",
        "retryable": False,
    }


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
