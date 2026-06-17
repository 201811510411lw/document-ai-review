import os
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel


PROJECT_ENV_KEYS = {
    "OPENAI_API_KEY",
    "OPENAI_API_KEY1",
    "OPENAI_BASE_URL",
    "OPENAI_API_BASE",
    "DOCUMENT_AI_REVIEW_DEBUG",
    "BUSINESS_LICENSE_VISION_PROVIDER",
    "BUSINESS_LICENSE_QWEN_OCR_MODEL",
    "BUSINESS_LICENSE_QWEN_OCR_TIMEOUT_SECONDS",
    "BUSINESS_LICENSE_QWEN_OCR_MAX_ATTEMPTS",
    "BUSINESS_LICENSE_QWEN_OCR_MAX_PAGES",
    "BUSINESS_LICENSE_QWEN_OCR_STOP_AFTER_FIRST_LICENSE",
    "BUSINESS_LICENSE_SKILL_REVIEW_PROVIDER",
    "BUSINESS_LICENSE_SKILL_REVIEW_MODEL",
    "BUSINESS_LICENSE_SKILL_REVIEW_FAKE_JSON",
    "FOOD_LICENSE_SKILL_REVIEW_PROVIDER",
    "FOOD_LICENSE_SKILL_REVIEW_MODEL",
    "FOOD_LICENSE_SKILL_REVIEW_FAKE_JSON",
    "QC_DOCUMENT_SKILL_REVIEW_PROVIDER",
    "QC_DOCUMENT_SKILL_REVIEW_MODEL",
    "QC_DOCUMENT_SKILL_REVIEW_FAKE_JSON",
    "ALIYUN_OCR_API_URL",
    "ALIYUN_OCR_APPCODE",
    "ALIYUN_OCR_IMAGE_FIELD",
    "ALIYUN_OCR_TIMEOUT_SECONDS",
    "ALIYUN_OCR_BODY_JSON",
    "ALIYUN_OCR_LLM_PARSE_MODEL",
    "ALIYUN_OCR_TRY_ROTATIONS",
    "ALIYUN_OCR_STOP_AFTER_FIRST_LICENSE",
    "ALIYUN_OCR_ROTATION_ORDER",
    "ALIYUN_OCR_LOCAL_PREFILTER_PROVIDER",
    "SRM_MYSQL_HOST",
    "SRM_MYSQL_PORT",
    "SRM_MYSQL_USER",
    "SRM_MYSQL_PASSWORD",
    "SRM_MYSQL_DATABASE",
    "REVIEW_RESULT_MYSQL_HOST",
    "REVIEW_RESULT_MYSQL_PORT",
    "REVIEW_RESULT_MYSQL_USER",
    "REVIEW_RESULT_MYSQL_PASSWORD",
    "REVIEW_RESULT_MYSQL_DATABASE",
    "WEB_CONSOLE_AUTH_USERNAME",
    "WEB_CONSOLE_AUTH_PASSWORD",
    "WEB_CONSOLE_AUTH_SECRET",
    "WEB_CONSOLE_AUTH_TOKEN_TTL_SECONDS",
    "WECOM_CORP_ID",
    "WECOM_AGENT_ID",
    "WECOM_SECRET",
    "WECOM_REDIRECT_URI",
    "WECOM_UNMATCHED_USER_POLICY",
    "WECOM_REVIEWER_USER_IDS",
    "WECOM_ADMIN_USER_IDS",
    "WECOM_WORKER_TOKEN",
    "WECOM_NOTIFICATION_BASE_URL",
    "WEB_CONSOLE_BASE_URL",
}


def load_local_env() -> None:
    project_root = Path(__file__).resolve().parents[3]
    env_values = {
        **dotenv_values(project_root / ".env"),
        **dotenv_values(project_root / "ai-service" / ".env"),
    }
    for key in PROJECT_ENV_KEYS:
        if key in os.environ:
            continue
        if key in env_values and env_values[key] is not None:
            os.environ[key] = env_values[key] or ""
    if not os.environ.get("OPENAI_API_KEY") and os.environ.get("OPENAI_API_KEY1"):
        os.environ["OPENAI_API_KEY"] = os.environ["OPENAI_API_KEY1"]


load_local_env()


class Settings(BaseModel):
    app_name: str = "document-ai-review ai-service"
    service_name: str = "ai-service"
    api_version: str = "v1"
    timezone: str = "Asia/Shanghai"
    web_console_auth_username: str = os.environ.get(
        "WEB_CONSOLE_AUTH_USERNAME", "reviewer"
    )
    web_console_auth_password: str = os.environ.get(
        "WEB_CONSOLE_AUTH_PASSWORD", "reviewer123"
    )
    web_console_auth_secret: str = os.environ.get(
        "WEB_CONSOLE_AUTH_SECRET", "document-ai-review-dev-secret"
    )
    web_console_auth_token_ttl_seconds: int = int(
        os.environ.get("WEB_CONSOLE_AUTH_TOKEN_TTL_SECONDS", "28800")
    )
    wecom_corp_id: str = os.environ.get("WECOM_CORP_ID", "")
    wecom_agent_id: str = os.environ.get("WECOM_AGENT_ID", "")
    wecom_secret: str = os.environ.get("WECOM_SECRET", "")
    wecom_redirect_uri: str = os.environ.get("WECOM_REDIRECT_URI", "")
    wecom_unmatched_user_policy: str = os.environ.get(
        "WECOM_UNMATCHED_USER_POLICY", "reject"
    )
    wecom_reviewer_user_ids: str = os.environ.get("WECOM_REVIEWER_USER_IDS", "")
    wecom_admin_user_ids: str = os.environ.get("WECOM_ADMIN_USER_IDS", "")
    wecom_worker_token: str = os.environ.get("WECOM_WORKER_TOKEN", "")
    wecom_notification_base_url: str = os.environ.get("WECOM_NOTIFICATION_BASE_URL", "")
    web_console_base_url: str = os.environ.get("WEB_CONSOLE_BASE_URL", "")


settings = Settings()
