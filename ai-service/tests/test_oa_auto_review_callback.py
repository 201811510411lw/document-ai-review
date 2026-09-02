import logging
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
    OaAutoReviewCallbackDelivery,
    OaAutoReviewCallbackError,
    OaAutoReviewCallbackPayload,
)
from app.services.oa_tobacco_auto_review import (
    OaAutoReviewCommand,
    OaAutoReviewError,
    OaAutoReviewOutcome,
    oa_auto_review_task_id,
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


class SubmissionSqlClient:
    source_tables = {"requestlog": "workflow_requestlog"}

    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error
        self.executed_sql = []

    def fetch_all(self, sql):
        self.executed_sql.append(sql)
        if self.error is not None:
            raise self.error
        return self.rows


class CompletedReviewService:
    def review(self, command):
        return OaAutoReviewOutcome(
            task_id=oa_auto_review_task_id(
                command.workflow_id,
                command.requestid,
                command.submission_version,
            ),
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
        sql_client=SubmissionSqlClient(),
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
            "submission_version": 1,
        },
    }
    assert len(background_tasks.tasks) == 1


def test_resubmission_log_creates_a_new_review_task_without_oa_version():
    background_tasks = CapturingBackgroundTasks()
    sql_client = SubmissionSqlClient([
        {"submission_log_id": 23811265, "submission_version": 2},
    ])

    response = submit_oa_auto_review(
        OaAutoReviewRequest(
            requestid=584412,
            store_code="0001",
            store_name="测试门店",
            workflow_id=123,
        ),
        background_tasks=background_tasks,
        _oa_client={"client": "oa"},
        sql_client=sql_client,
        file_store=object(),
        repository=object(),
        document_review_service=object(),
        callback_client=CapturingCallbackClient(),
    )

    assert response["data"] == {
        "status": "processing",
        "task_id": "tc-oa-123-584412-s2",
        "workflow_id": 123,
        "submission_version": 2,
    }
    command = background_tasks.tasks[0][2]["command"]
    assert command.submission_version == 2
    assert command.submission_log_id == 23811265
    assert "FROM workflow_requestlog" in sql_client.executed_sql[0]


def test_submission_identity_query_failure_does_not_replay_first_submission():
    background_tasks = CapturingBackgroundTasks()

    with pytest.raises(HTTPException) as error:
        submit_oa_auto_review(
            OaAutoReviewRequest(
                requestid=584412,
                store_code="0001",
                workflow_id=123,
            ),
            background_tasks=background_tasks,
            _oa_client={"client": "oa"},
            sql_client=SubmissionSqlClient(error=RuntimeError("database unavailable")),
            file_store=object(),
            repository=object(),
            document_review_service=object(),
            callback_client=CapturingCallbackClient(),
        )

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "OA_SUBMISSION_IDENTITY_UNAVAILABLE"
    assert background_tasks.tasks == []


def test_explicit_submission_version_remains_supported_without_querying_oa_log():
    background_tasks = CapturingBackgroundTasks()
    sql_client = SubmissionSqlClient(error=AssertionError("must not query"))

    response = submit_oa_auto_review(
        OaAutoReviewRequest(
            requestid=584412,
            store_code="0001",
            workflow_id=123,
            submission_version=3,
        ),
        background_tasks=background_tasks,
        _oa_client={"client": "oa"},
        sql_client=sql_client,
        file_store=object(),
        repository=object(),
        document_review_service=object(),
        callback_client=CapturingCallbackClient(),
    )

    assert response["data"]["task_id"] == "tc-oa-123-584412-s3"
    assert sql_client.executed_sql == []


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


def test_resubmission_callback_carries_submission_identity():
    command = OaAutoReviewCommand(
        requestid=584412,
        store_code="0001",
        store_name="测试门店",
        workflow_id=123,
        submission_version=2,
    )
    callback_client = CapturingCallbackClient()

    _run_oa_auto_review_and_callback(
        command=command,
        review_service=CompletedReviewService(),
        callback_client=callback_client,
    )

    payload = callback_client.payloads[0]
    assert payload.submission_version == 2
    assert payload.result["data"]["task_id"] == "tc-oa-123-584412-s2"


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


def test_callback_client_posts_json_without_authentication(monkeypatch, caplog):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            200,
            json={"code": 0, "message": "received"},
            request=httpx.Request("POST", url),
        )

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

    with caplog.at_level(logging.INFO, logger="app.services.oa_auto_review_callback"):
        delivery = client.send(payload)

    url, kwargs = calls[0]
    assert url == "http://47.109.76.94:8080/api/bicallback/result"
    assert kwargs["json"]["workflow_id"] == 123
    assert kwargs["headers"] == {"Content-Type": "application/json"}
    assert "auth" not in kwargs
    assert delivery == OaAutoReviewCallbackDelivery(
        target="http://47.109.76.94:8080/api/bicallback/result",
        attempt_count=1,
        http_status=200,
        response_body={"code": 0, "message": "received"},
        business_accepted=True,
    )
    assert (
        "[OA自动审核][回调开始] workflow_id=123 requestid=584412 "
        "门店=0001 第1/3次 目标=http://47.109.76.94:8080/api/bicallback/result"
        ) in caplog.messages
    assert any(
        message.startswith(
            "[OA自动审核][回调成功] workflow_id=123 requestid=584412 "
            "门店=0001 第1/3次 HTTP状态=200 耗时="
        )
        for message in caplog.messages
    )


def test_callback_client_retries_network_and_server_errors(monkeypatch, caplog):
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

    with caplog.at_level(logging.INFO, logger="app.services.oa_auto_review_callback"):
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
    assert any(
        "[OA自动审核][回调网络异常] workflow_id=123 requestid=584412 "
        "门店=0001 第1/3次 异常类型=ConnectError 耗时="
        in message
        for message in caplog.messages
    )
    assert any(
        "[OA自动审核][回调可重试失败] workflow_id=123 requestid=584412 "
        "门店=0001 第2/3次 HTTP状态=503 耗时="
        in message
        for message in caplog.messages
    )
    assert not any("success" in message for message in caplog.messages)


def test_callback_logs_omit_url_query_parameters(monkeypatch, caplog):
    callback_url = (
        "http://47.109.76.94:8080/api/bicallback/result?access_token=do-not-log"
    )

    def post(url, **kwargs):
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.services.oa_auto_review_callback.httpx.post", post)
    client = HttpOaAutoReviewCallbackClient(callback_url, sleep=lambda _: None)

    with caplog.at_level(logging.INFO, logger="app.services.oa_auto_review_callback"):
        client.send(
            OaAutoReviewCallbackPayload(
                workflow_id=123,
                requestid=584412,
                store_code="0001",
                result={"code": 0, "message": "success", "data": {}},
            )
        )

    assert "目标=http://47.109.76.94:8080/api/bicallback/result" in caplog.text
    assert "access_token" not in caplog.text
    assert "do-not-log" not in caplog.text


def test_callback_logs_non_retryable_rejection(monkeypatch, caplog):
    callback_url = "http://47.109.76.94:8080/api/bicallback/result"

    def post(url, **kwargs):
        return httpx.Response(400, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.services.oa_auto_review_callback.httpx.post", post)
    client = HttpOaAutoReviewCallbackClient(callback_url, sleep=lambda _: None)

    with caplog.at_level(logging.INFO, logger="app.services.oa_auto_review_callback"):
        with pytest.raises(
            OaAutoReviewCallbackError,
            match="OA callback rejected payload with HTTP 400",
        ):
            client.send(
                OaAutoReviewCallbackPayload(
                    workflow_id=123,
                    requestid=584412,
                    store_code="0001",
                    result={"code": 0, "message": "success", "data": {}},
                )
            )

    assert any(
        "[OA自动审核][回调被拒绝] workflow_id=123 requestid=584412 "
        "门店=0001 第1/3次 HTTP状态=400 耗时=" in message
        for message in caplog.messages
    )


def test_callback_logs_all_attempts_before_retry_exhaustion(monkeypatch, caplog):
    callback_url = "http://47.109.76.94:8080/api/bicallback/result"

    def post(url, **kwargs):
        return httpx.Response(500, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.services.oa_auto_review_callback.httpx.post", post)
    client = HttpOaAutoReviewCallbackClient(callback_url, sleep=lambda _: None)
    payload = OaAutoReviewCallbackPayload(
        workflow_id=123,
        requestid=584412,
        store_code="0001",
        result={"code": 0, "message": "success", "data": {}},
    )

    with caplog.at_level(logging.INFO, logger="app.services.oa_auto_review_callback"):
        with pytest.raises(
            OaAutoReviewCallbackError,
            match="OA callback delivery failed after 3 attempts",
        ):
            client.send(payload)

    assert sum("[OA自动审核][回调开始]" in message for message in caplog.messages) == 3
    assert (
        sum("[OA自动审核][回调可重试失败]" in message for message in caplog.messages)
        == 3
    )
    assert any("第3/3次 HTTP状态=500" in message for message in caplog.messages)


def test_callback_client_requires_server_side_url(monkeypatch):
    monkeypatch.setattr(settings, "oa_auto_review_callback_url", "")

    with pytest.raises(HTTPException) as error:
        get_oa_auto_review_callback_client()

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "OA_CALLBACK_NOT_CONFIGURED"


def test_callback_client_records_unconfirmed_empty_2xx_response(monkeypatch):
    callback_url = "http://47.109.76.94:8080/api/bicallback/result"

    def post(url, **kwargs):
        return httpx.Response(200, content=b"", request=httpx.Request("POST", url))

    monkeypatch.setattr("app.services.oa_auto_review_callback.httpx.post", post)
    delivery = HttpOaAutoReviewCallbackClient(
        callback_url, sleep=lambda _: None
    ).send(
        OaAutoReviewCallbackPayload(
            workflow_id=614,
            requestid=584412,
            store_code="0001",
            result={"code": 0, "message": "success", "data": {}},
        )
    )

    assert delivery.http_status == 200
    assert delivery.response_body is None
    assert delivery.business_accepted is None


def test_callback_client_rejects_explicit_business_failure_in_http_2xx(monkeypatch):
    callback_url = "http://47.109.76.94:8080/api/bicallback/result"

    def post(url, **kwargs):
        return httpx.Response(
            200,
            json={"code": 500, "message": "OA node not found"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.services.oa_auto_review_callback.httpx.post", post)
    client = HttpOaAutoReviewCallbackClient(callback_url, sleep=lambda _: None)

    with pytest.raises(
        OaAutoReviewCallbackError,
        match="OA callback business response rejected payload",
    ) as captured:
        client.send(
            OaAutoReviewCallbackPayload(
                workflow_id=614,
                requestid=584412,
                store_code="0001",
                result={"code": 0, "message": "success", "data": {}},
            )
        )

    assert captured.value.delivery.http_status == 200
    assert captured.value.delivery.response_body == {
        "code": 500,
        "message": "OA node not found",
    }
    assert captured.value.delivery.business_accepted is False


def _review_result(command):
    now = datetime(2026, 8, 5, tzinfo=timezone.utc)
    return ReviewResult(
        task_id=oa_auto_review_task_id(
            command.workflow_id,
            command.requestid,
            command.submission_version,
        ),
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
