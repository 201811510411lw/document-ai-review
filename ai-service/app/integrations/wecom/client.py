from dataclasses import dataclass
from time import time
from typing import Any
from urllib.parse import urlencode

import requests

from app.core.config import settings


QR_CONNECT_URL = "https://open.work.weixin.qq.com/wwopen/sso/qrConnect"
WORK_OAUTH_URL = "https://open.weixin.qq.com/connect/oauth2/authorize"
API_BASE_URL = "https://qyapi.weixin.qq.com/cgi-bin"


@dataclass(frozen=True)
class WecomConfig:
    corp_id: str
    agent_id: str
    secret: str
    redirect_uri: str


@dataclass(frozen=True)
class WecomUser:
    user_id: str
    name: str
    email: str
    department_ids: tuple[int, ...] = ()
    tag_ids: tuple[int, ...] = ()


class WecomConfigError(RuntimeError):
    pass


class WecomApiError(RuntimeError):
    def __init__(self, operation: str, errcode: int, errmsg: str) -> None:
        super().__init__(f"{operation}: {errmsg or errcode} (errcode: {errcode})")
        self.operation = operation
        self.errcode = errcode
        self.errmsg = errmsg


class WecomHttpError(RuntimeError):
    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"企业微信接口请求失败: {status_code}: {body}")
        self.status_code = status_code
        self.body = body


class WecomClient:
    def __init__(self, config: WecomConfig | None = None) -> None:
        self.config = config or require_wecom_config()
        self._token: str | None = None
        self._token_expires_at = 0.0

    def build_authorize_url(self, state: str) -> str:
        return f"{QR_CONNECT_URL}?{urlencode({
            'appid': self.config.corp_id,
            'agentid': self.config.agent_id,
            'redirect_uri': self.config.redirect_uri,
            'state': state,
        })}"

    def build_work_authorize_url(self, state: str) -> str:
        return f"{WORK_OAUTH_URL}?{urlencode({
            'appid': self.config.corp_id,
            'redirect_uri': self.config.redirect_uri,
            'response_type': 'code',
            'scope': 'snsapi_base',
            'state': state,
        })}#wechat_redirect"

    def resolve_login_user(self, code: str) -> WecomUser:
        if not code.strip():
            raise ValueError("企业微信回调缺少 code")
        token = self.get_access_token()
        user_info = self._get_json(
            f"{API_BASE_URL}/auth/getuserinfo",
            {"access_token": token, "code": code},
        )
        _assert_wecom_ok(user_info, "获取企业微信登录用户失败")
        user_id = str(user_info.get("userid") or user_info.get("UserId") or "").strip()
        if not user_id:
            raise ValueError("企业微信未返回 UserId，请确认应用可见范围")
        detail = self._get_json(
            f"{API_BASE_URL}/user/get",
            {"access_token": token, "userid": user_id},
        )
        _assert_wecom_ok(detail, "获取企业微信用户详情失败")
        return WecomUser(
            user_id=user_id,
            name=str(detail.get("name") or user_id),
            email=str(detail.get("email") or detail.get("biz_mail") or f"{user_id}@wecom.local"),
            department_ids=tuple(int(item) for item in detail.get("department") or ()),
            tag_ids=tuple(int(item) for item in detail.get("tagid") or ()),
        )

    def send_text_message(self, to_user_ids: list[str], content: str) -> None:
        unique_user_ids = [item for item in dict.fromkeys(item.strip() for item in to_user_ids) if item]
        if not unique_user_ids:
            raise ValueError("企业微信通知缺少接收人")
        token = self.get_access_token()
        payload = {
            "touser": "|".join(unique_user_ids),
            "msgtype": "text",
            "agentid": int(self.config.agent_id),
            "text": {"content": content},
            "safe": 0,
            "enable_duplicate_check": 1,
        }
        result = self._post_json(
            f"{API_BASE_URL}/message/send?access_token={token}",
            payload,
        )
        _assert_wecom_ok(result, "发送企业微信应用消息失败")

    def get_access_token(self) -> str:
        if self._token and self._token_expires_at > time() + 60:
            return self._token
        payload = self._get_json(
            f"{API_BASE_URL}/gettoken",
            {"corpid": self.config.corp_id, "corpsecret": self.config.secret},
        )
        _assert_wecom_ok(payload, "获取企业微信 access_token 失败")
        token = str(payload.get("access_token") or "")
        if not token:
            raise WecomApiError("获取企业微信 access_token 失败", -1, "未返回 access_token")
        self._token = token
        self._token_expires_at = time() + max(60, int(payload.get("expires_in") or 7200) - 120)
        return token

    def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        response = requests.get(url, params=params, timeout=10)
        if not response.ok:
            raise WecomHttpError(response.status_code, response.text)
        return dict(response.json())

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(url, json=payload, timeout=10)
        if not response.ok:
            raise WecomHttpError(response.status_code, response.text)
        return dict(response.json())


def get_wecom_config() -> WecomConfig | None:
    corp_id = settings.wecom_corp_id.strip()
    agent_id = settings.wecom_agent_id.strip()
    secret = settings.wecom_secret.strip()
    redirect_uri = settings.wecom_redirect_uri.strip()
    if not corp_id or not agent_id or not secret or not redirect_uri:
        return None
    return WecomConfig(
        corp_id=corp_id,
        agent_id=agent_id,
        secret=secret,
        redirect_uri=redirect_uri,
    )


def require_wecom_config() -> WecomConfig:
    config = get_wecom_config()
    if config is None:
        raise WecomConfigError(
            "企业微信应用未配置 WECOM_CORP_ID/WECOM_AGENT_ID/WECOM_SECRET/WECOM_REDIRECT_URI"
        )
    return config


def _assert_wecom_ok(payload: dict[str, Any], operation: str) -> None:
    errcode = int(payload.get("errcode") or 0)
    if errcode:
        raise WecomApiError(operation, errcode, str(payload.get("errmsg") or ""))
