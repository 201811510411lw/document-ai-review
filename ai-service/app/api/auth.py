from base64 import urlsafe_b64decode, urlsafe_b64encode
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
from json import dumps, loads
from secrets import token_urlsafe
from time import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.core.config import settings
from app.integrations.wecom.client import (
    WecomApiError,
    WecomClient,
    WecomConfigError,
    WecomHttpError,
    WecomUser,
    get_wecom_config,
)


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
SESSION_COOKIE_NAME = "document_ai_review_session"


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(request: LoginRequest) -> dict[str, Any]:
    if not _valid_credentials(request.username, request.password):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "INVALID_CREDENTIALS",
                "message": "用户名或密码错误",
            },
        )
    expires_at = int(time()) + settings.web_console_auth_token_ttl_seconds
    user = {
        "username": request.username,
        "display_name": "审核员",
    }
    return {
        "access_token": _sign_token({**user, "expires_at": expires_at}),
        "token_type": "bearer",
        "expires_at": expires_at,
        "user": user,
    }


@router.get("/providers")
def auth_providers() -> dict[str, Any]:
    configured = get_wecom_config() is not None
    return {
        "providers": [
            {
                "id": "wecom",
                "label": "企业微信",
                "type": "OAuth2",
                "configured": configured,
                "login_path": "/api/v1/auth/sso/start?provider=wecom",
                "callback_path": "/api/v1/auth/sso/callback?provider=wecom",
                "status": "已配置，可发起真实 OAuth 授权" if configured else "待配置真实企业微信应用",
            }
        ]
    }


@router.get("/sso/start")
def start_sso(
    provider: str = Query(default="wecom"),
    mode: str = Query(default="qr"),
) -> dict[str, Any]:
    if provider != "wecom":
        raise HTTPException(
            status_code=501,
            detail={"code": "SSO_NOT_IMPLEMENTED", "message": "当前仅支持企业微信 SSO"},
        )
    if mode not in {"qr", "work"}:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_SSO_MODE", "message": "企业微信登录模式不支持"},
        )
    try:
        state = _create_sso_state(provider)
        client = WecomClient()
        redirect_url = (
            client.build_work_authorize_url(state)
            if mode == "work"
            else client.build_authorize_url(state)
        )
    except WecomConfigError as error:
        raise HTTPException(
            status_code=503,
            detail={"code": "SSO_NOT_CONFIGURED", "message": str(error)},
        ) from error
    return {"redirect_url": redirect_url}


@router.get("/sso/callback")
def sso_callback(
    provider: str = Query(default="wecom"),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
) -> Response:
    if provider != "wecom":
        raise HTTPException(
            status_code=501,
            detail={"code": "SSO_NOT_IMPLEMENTED", "message": "当前仅支持企业微信 SSO"},
        )
    if not code and not state:
        return RedirectResponse(_post_login_redirect_url(), status_code=302)
    if not _consume_sso_state(provider, state):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_SSO_STATE", "message": "登录状态已失效，请重新扫码"},
        )
    if not code:
        raise HTTPException(
            status_code=400,
            detail={"code": "MISSING_SSO_CODE", "message": "企业微信回调缺少 code"},
        )
    try:
        wecom_user = WecomClient().resolve_login_user(code)
        user = _map_wecom_user(wecom_user)
    except WecomApiError as error:
        raise _wecom_api_http_exception(error) from error
    except WecomHttpError as error:
        raise HTTPException(
            status_code=502,
            detail={"code": "WECOM_HTTP_ERROR", "message": str(error)},
        ) from error
    except WecomConfigError as error:
        raise HTTPException(
            status_code=503,
            detail={"code": "SSO_NOT_CONFIGURED", "message": str(error)},
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=403,
            detail={"code": "WECOM_AUTH_FAILED", "message": str(error)},
        ) from error

    expires_at = int(time()) + settings.web_console_auth_token_ttl_seconds
    access_token = _sign_token({**user, "expires_at": expires_at})
    response = RedirectResponse(_post_login_redirect_url(), status_code=302)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        access_token,
        max_age=settings.web_console_auth_token_ttl_seconds,
        httponly=True,
        samesite="lax",
    )
    return response


def require_web_console_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = _bearer_token(authorization) or request.cookies.get(SESSION_COOKIE_NAME)
    if token is None:
        raise _unauthorized()
    payload = _verify_token(token)
    if payload is None:
        raise _unauthorized()
    return {
        "username": str(payload.get("username") or ""),
        "display_name": str(payload.get("display_name") or payload.get("username") or ""),
        "provider": str(payload.get("provider") or "local"),
        "external_id": str(payload.get("external_id") or ""),
        "email": str(payload.get("email") or ""),
    }


@router.get("/me")
def me(current_user: dict[str, Any] = Depends(require_web_console_user)) -> dict[str, Any]:
    return {"user": current_user}


def _valid_credentials(username: str, password: str) -> bool:
    return compare_digest(username, settings.web_console_auth_username) and compare_digest(
        password,
        settings.web_console_auth_password,
    )


def _create_sso_state(provider: str) -> str:
    payload = f"{int(time()) + 600}.{provider}.{token_urlsafe(8)}"
    payload_part = _encode(payload.encode("utf-8"))
    return f"{payload_part}.{_signature(payload_part)[:16]}"


def _consume_sso_state(provider: str, state: str | None) -> bool:
    if not state:
        return False
    return _consume_short_sso_state(provider, state) or _consume_legacy_signed_sso_state(
        provider,
        state,
    )


def _consume_short_sso_state(provider: str, state: str) -> bool:
    payload_part, separator, signature = state.partition(".")
    if not separator or not payload_part or not signature:
        return False
    if len(signature) != 16 or not compare_digest(signature, _signature(payload_part)[:16]):
        return False
    try:
        expires_at, state_provider, _nonce = (
            urlsafe_b64decode(_pad_base64(payload_part)).decode("utf-8").split(".", 2)
        )
    except (ValueError, TypeError):
        return False
    if state_provider != provider:
        return False
    if int(expires_at or 0) < int(time()):
        return False
    return True


def _consume_legacy_signed_sso_state(provider: str, state: str) -> bool:
    record = _verify_token(state)
    if record is None:
        return False
    if record.get("provider") != provider:
        return False
    return True


def _map_wecom_user(wecom_user: WecomUser) -> dict[str, Any]:
    # 登录准入交给企业微信自建应用可见范围控制；本系统只记录企微身份用于审计。
    return {
        "username": wecom_user.user_id,
        "display_name": wecom_user.name,
        "provider": "wecom",
        "external_id": wecom_user.user_id,
        "email": wecom_user.email,
    }


def _wecom_api_http_exception(error: WecomApiError) -> HTTPException:
    if error.errcode == 60020:
        return HTTPException(
            status_code=403,
            detail={"code": "WECOM_IP_NOT_ALLOWED", "message": str(error)},
        )
    if error.errcode in {40029, 40014, 42001}:
        return HTTPException(
            status_code=400,
            detail={"code": "WECOM_CODE_INVALID", "message": "企业微信授权已失效，请重新扫码"},
        )
    if error.errcode in {40001, 40013, 48002}:
        return HTTPException(
            status_code=502,
            detail={"code": "WECOM_CONFIG_INVALID", "message": str(error)},
        )
    if error.errcode in {60111, 60121}:
        return HTTPException(
            status_code=403,
            detail={"code": "WECOM_USER_NOT_VISIBLE", "message": str(error)},
        )
    return HTTPException(
        status_code=502,
        detail={"code": "WECOM_API_ERROR", "message": str(error)},
    )


def _post_login_redirect_url() -> str:
    base_url = settings.web_console_base_url.strip().rstrip("/")
    if base_url:
        return f"{base_url}/reviews"
    return "/reviews"


def _sign_token(payload: dict[str, Any]) -> str:
    payload_json = dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload_part = _encode(payload_json.encode("utf-8"))
    signature = _signature(payload_part)
    return f"{payload_part}.{signature}"


def _verify_token(token: str) -> dict[str, Any] | None:
    payload_part, separator, signature = token.partition(".")
    if not separator or not payload_part or not signature:
        return None
    if not compare_digest(signature, _signature(payload_part)):
        return None
    try:
        payload = loads(urlsafe_b64decode(_pad_base64(payload_part)).decode("utf-8"))
    except (ValueError, TypeError):
        return None
    if int(payload.get("expires_at") or 0) < int(time()):
        return None
    return payload


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _signature(payload_part: str) -> str:
    digest = hmac_new(
        settings.web_console_auth_secret.encode("utf-8"),
        payload_part.encode("utf-8"),
        sha256,
    ).digest()
    return _encode(digest)


def _encode(value: bytes) -> str:
    return urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _pad_base64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return f"{value}{padding}".encode("ascii")


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={
            "code": "UNAUTHORIZED",
            "message": "请先登录工作台",
        },
    )
