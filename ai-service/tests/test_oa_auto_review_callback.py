from datetime import datetime, timezone

import httpx
import pytest
from fastapi import HTTPException

from app.api.tobacco_license_consistency import (
    OaAutoReviewRequest,
    _run_oa_auto_review_and_callback,
    get_oa_auto_review_callback_client,
    submit_oa_auto_review,
)
from app.core.config import settings
from app.models import ManualReview, ManualReviewStatus, ReviewResult, ReviewStatus, RiskLevel
from app.services.oa_auto_review_callback import (
    HttpOaAutoReviewCallbackClient,
    OaAutoReviewCallbackPayload,
)
from app.services.oa_tobacco_auto_review import (
    OaAutoReviewCommand,
    OaAutoReviewError,
    OaAutoReviewOutcome,
)


class CapturingBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, function, *args, **kwargs):
        self.tasks.append((function, args, kwargs))


class CapturingCallbackClient:
    def __init__(self):
        self.payloads = []

    def send(self, payload):
        self.payloads.append(payload)


class CompletedReviewService:
    def review(self, command):
        return OaAutoReviewOutcome(
            task_id=f"tc-oa-{command.workflow_id}-{command.requestid}",
            result=_review_result(command),
        )


class RunningReviewService:
    def review(self, command):
        return OaAutoReviewOutcome(
            task_id=f"tc-oa-{command.workflow_id}-{command.requestid}",
            error=OaAutoReviewError(
                code="REVIEW_IN_PROGRESS",
                message="自动审核正在执行，请稍后轮询",
                retryable=True,
            ),
        )


def test_submit_returns_processing_and_schedules_background_review():
    background_tasks = CapturingBackgroundTasks()
    callback_client = CapturingCallbackClient()

    response = submit_oa_auto_review(
        OaAutoReviewRequest(
            requestid=584412,
            store_code="0001",
            store_name="测试门店",
            workflow_id=123,
        ),
        background_tasks=background_tasks,
        _oa_client={"client": "oa"},
        sql_client=object(),
        file_store=object(),
        repository=object(),
        document_review_service=object(),
        callback_client=callback_client,
    )

    assert response == {
        "code": 0,
        "message": "accepted",
        "data": {
            "status": "processing",
            "task_id": "tc-oa-123-584412",
            "workflow_id": 123,
        },
    }
    assert len(background_tasks.tasks) == 1


def test_background_review_posts_result_with_original_oa_identity():
    command = OaAutoReviewCommand(
        requestid=584412,
        store_code="0001",
        store_name="测试门店",
        workflow_id=123,
    )
    callback_client = CapturingCallbackClient()

    _run_oa_auto_review_and_callback(
        command=command,
        review_service=CompletedReviewService(),
        callback_client=callback_client,
    )

    payload = callback_client.payloads[0]
    assert payload.workflow_id == 123
    assert payload.requestid == 584412
    assert payload.store_code == "0001"
    assert payload.result["data"]["decision"] == "pass"
    assert payload.result["data"]["task_id"] == "tc-oa-123-584412"


def test_duplicate_background_review_does_not_callback_in_progress_as_final_result():
    callback_client = CapturingCallbackClient()

    _run_oa_auto_review_and_callback(
        command=OaAutoReviewCommand(
            requestid=584412,
            store_code="0001",
            store_name="测试门店",
            workflow_id=123,
        ),
        review_service=RunningReviewService(),
        callback_client=callback_client,
    )

    assert callback_client.payloads == []


def test_callback_client_posts_json_without_authentication(monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.services.oa_auto_review_callback.httpx.post", post)
    client = HttpOaAutoReviewCallbackClient(
        "http://47.109.76.94:8080/api/bicallback/result",
        sleep=lambda _: None,
    )
    payload = OaAutoReviewCallbackPayload(
        workflow_id=123,
        requestid=584412,
        store_code="0001",
        result={"code": 0, "message": "success", "data": {"decision": "pass"}},
    )

    client.send(payload)

    url, kwargs = calls[0]
    assert url == "http://47.109.76.94:8080/api/bicallback/result"
    assert kwargs["json"]["workflow_id"] == 123
    assert kwargs["headers"] == {"Content-Type": "application/json"}
    assert "auth" not in kwargs


def test_callback_client_retries_network_and_server_errors(monkeypatch):
    responses = [
        httpx.ConnectError("unreachable"),
        httpx.Response(
            503,
            request=httpx.Request(
                "POST", "http://47.109.76.94:8080/api/bicallback/result"
            ),
        ),
        httpx.Response(
            200,
            request=httpx.Request(
                "POST", "http://47.109.76.94:8080/api/bicallback/result"
            ),
        ),
    ]

    def post(url, **kwargs):
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("app.services.oa_auto_review_callback.httpx.post", post)
    sleeps = []
    client = HttpOaAutoReviewCallbackClient(
        "http://47.109.76.94:8080/api/bicallback/result",
        sleep=sleeps.append,
    )

    client.send(
        OaAutoReviewCallbackPayload(
            workflow_id=123,
            requestid=584412,
            store_code="0001",
            result={"code": 0, "message": "success", "data": {}},
        )
    )

    assert responses == []
    assert sleeps == [1.0, 5.0]


def test_callback_client_requires_server_side_url(monkeypatch):
    monkeypatch.setattr(settings, "oa_auto_review_callback_url", "")

    with pytest.raises(HTTPException) as error:
        get_oa_auto_review_callback_client()

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "OA_CALLBACK_NOT_CONFIGURED"


def _review_result(command):
    now = datetime(2026, 8, 5, tzinfo=timezone.utc)
    return ReviewResult(
        task_id=f"tc-oa-{command.workflow_id}-{command.requestid}",
        use_case_name="tobacco_license_consistency_review",
        use_case_version="v1",
        skill_name="tobacco_license_consistency_review",
        skill_version="v1",
        ruleset_version="v1",
        document_type="business_tobacco_consistency",
        status=ReviewStatus.REVIEWED,
        risk_level=RiskLevel.NONE,
        needs_manual_review=False,
        rule_results=[],
        summary="营业执照与烟草证一致性校验通过",
        manual_review=ManualReview(status=ManualReviewStatus.NOT_REQUIRED),
        created_at=now,
        updated_at=now,
        skill_result={},
    )
