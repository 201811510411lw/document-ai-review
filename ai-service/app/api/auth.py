from base64 import urlsafe_b64decode, urlsafe_b64encode
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
from json import dumps, loads
from time import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.core.config import settings


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


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


def require_web_console_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = _bearer_token(authorization)
    if token is None:
        raise _unauthorized()
    payload = _verify_token(token)
    if payload is None:
        raise _unauthorized()
    return {
        "username": str(payload.get("username") or ""),
        "display_name": str(payload.get("display_name") or payload.get("username") or ""),
    }


@router.get("/me")
def me(current_user: dict[str, Any] = Depends(require_web_console_user)) -> dict[str, Any]:
    return {"user": current_user}


def _valid_credentials(username: str, password: str) -> bool:
    return compare_digest(username, settings.web_console_auth_username) and compare_digest(
        password,
        settings.web_console_auth_password,
    )


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
