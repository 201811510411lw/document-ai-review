import httpx
import pytest

from app.models.rpa import RpaVerificationStatus
from app.services.rpa_verification import YindaoRpaClient


def _client() -> YindaoRpaClient:
    return YindaoRpaClient(
        api_base_url="https://api.yingdao.com",
        access_key_id="access-key-id",
        access_key_secret="access-key-secret",
        robot_uuid="robot-uuid",
    )


def _response(payload: dict) -> httpx.Response:
    return httpx.Response(
        status_code=200,
        json=payload,
        request=httpx.Request("POST", "https://api.yingdao.com/test"),
    )


def test_start_job_reads_job_uuid_from_response_data(monkeypatch):
    monkeypatch.setattr(
        "app.services.rpa_verification.httpx.post",
        lambda *args, **kwargs: _response(
            {
                "success": True,
                "code": 200,
                "data": {
                    "jobUuid": "job-123",
                    "idempotentFlag": False,
                },
            }
        ),
    )

    job_uuid = _client()._start_job(
        token="token",
        certificate_no="652328100481",
        store_name="测试门店",
    )

    assert job_uuid == "job-123"


def test_start_job_surfaces_yindao_business_error(monkeypatch):
    monkeypatch.setattr(
        "app.services.rpa_verification.httpx.post",
        lambda *args, **kwargs: _response(
            {
                "success": False,
                "code": 40001,
                "message": "机器人账号不存在",
                "requestId": "request-123",
            }
        ),
    )

    with pytest.raises(
        RuntimeError,
        match=r"影刀启动接口返回失败.*40001.*机器人账号不存在.*request-123",
    ):
        _client()._start_job(
            token="token",
            certificate_no="652328100481",
            store_name="测试门店",
        )


def test_query_job_returns_nested_response_data(monkeypatch):
    def fake_post(url, **kwargs):
        assert url == "https://api.yingdao.com/oapi/dispatch/v2/job/query"
        assert kwargs["json"] == {"jobUuid": "job-123"}
        assert "params" not in kwargs
        return _response(
            {
                "success": True,
                "code": 200,
                "data": {
                    "jobUuid": "job-123",
                    "status": "finish",
                    "result": [],
                },
            }
        )

    monkeypatch.setattr(
        "app.services.rpa_verification.httpx.post",
        fake_post,
    )

    result = _client()._query_job(token="token", job_uuid="job-123")

    assert result == {
        "jobUuid": "job-123",
        "status": "finish",
        "result": [],
    }


def test_map_result_reads_outputs_from_query_robot_params():
    result = _client()._map_result(
        certificate_no="652328100481",
        job_uuid="job-123",
        raw={
            "jobUuid": "job-123",
            "status": "finish",
            "robotParams": {
                "inputs": [],
                "outputs": [
                    {"name": "verify_status", "type": "str", "value": "AUTHENTIC"},
                    {"name": "screenshot_url", "type": "str", "value": "https://example.test/result.png"},
                ],
            },
        },
    )

    assert result.status == RpaVerificationStatus.AUTHENTIC
    assert result.screenshot_url == "https://example.test/result.png"


@pytest.mark.parametrize("parameter", [True, "true"])
def test_map_result_treats_true_parameter_as_authentic(parameter):
    result = _client()._map_result(
        certificate_no="652328100481",
        job_uuid="job-123",
        raw={
            "jobUuid": "job-123",
            "status": "finish",
            "robotParams": {
                "outputs": [
                    {"name": "parameter", "type": "str", "value": parameter},
                    {"name": "responseId", "type": "str", "value": "response-123"},
                ],
            },
        },
    )

    assert result.status == RpaVerificationStatus.AUTHENTIC
    assert result.error_message is None


@pytest.mark.parametrize("parameter", [False, "false"])
def test_map_result_treats_false_parameter_with_response_id_as_failure(parameter):
    result = _client()._map_result(
        certificate_no="652328100481",
        job_uuid="job-123",
        raw={
            "jobUuid": "job-123",
            "status": "finish",
            "robotParams": {
                "outputs": [
                    {"name": "parameter", "type": "str", "value": parameter},
                    {"name": "responseId", "type": "str", "value": "response-123"},
                ],
            },
        },
    )

    assert result.status == RpaVerificationStatus.FAILED
    assert result.result_label == "官网验真未通过"
    assert result.error_message == "官网验真未通过，影刀未返回具体原因"


@pytest.mark.parametrize("parameter", [False, "false"])
def test_map_result_treats_false_parameter_without_response_id_as_error(parameter):
    result = _client()._map_result(
        certificate_no="652328100481",
        job_uuid="job-123",
        raw={
            "jobUuid": "job-123",
            "status": "finish",
            "robotParams": {
                "outputs": [
                    {"name": "parameter", "type": "str", "value": parameter},
                    {"name": "responseId", "type": "str", "value": ""},
                ],
            },
        },
    )

    assert result.status == RpaVerificationStatus.ERROR
    assert result.result_label == "验真异常"
    assert result.error_message == "验真未完成：影刀未返回官网请求 ID"
