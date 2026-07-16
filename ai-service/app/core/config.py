import os
import json
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pydantic import BaseModel
import yaml


CONFIG_KEY_PATHS = {
    "DOCUMENT_AI_REVIEW_DEBUG": ("runtime", "debug"),
    "WEB_CONSOLE_BASE_URL": ("runtime", "web_console_base_url"),
    "OPENAI_BASE_URL": ("openai", "base_url"),
    "OPENAI_API_BASE": ("openai", "api_base"),
    "OPENAI_MAX_ATTEMPTS": ("openai", "max_attempts"),
    "BUSINESS_LICENSE_VISION_PROVIDER": ("business_license", "vision", "provider"),
    "BUSINESS_LICENSE_QWEN_OCR_MODEL": ("business_license", "qwen_ocr", "model"),
    "BUSINESS_LICENSE_QWEN_OCR_TIMEOUT_SECONDS": (
        "business_license",
        "qwen_ocr",
        "timeout_seconds",
    ),
    "BUSINESS_LICENSE_QWEN_OCR_MAX_ATTEMPTS": (
        "business_license",
        "qwen_ocr",
        "max_attempts",
    ),
    "BUSINESS_LICENSE_QWEN_OCR_MAX_PAGES": (
        "business_license",
        "qwen_ocr",
        "max_pages",
    ),
    "BUSINESS_LICENSE_QWEN_OCR_STOP_AFTER_FIRST_LICENSE": (
        "business_license",
        "qwen_ocr",
        "stop_after_first_license",
    ),
    "BUSINESS_LICENSE_SKILL_REVIEW_MODEL": (
        "business_license",
        "skill_review_model",
    ),
    "BUSINESS_LICENSE_MAX_FILE_BYTES": (
        "business_license",
        "guardrails",
        "max_file_bytes",
    ),
    "BUSINESS_LICENSE_MAX_PDF_PAGES": (
        "business_license",
        "guardrails",
        "max_pdf_pages",
    ),
    "BUSINESS_LICENSE_MAX_IMAGE_PIXELS": (
        "business_license",
        "guardrails",
        "max_image_pixels",
    ),
    "FOOD_LICENSE_FILE_RECOGNITION_PROVIDER": (
        "food_license",
        "file_recognition",
        "provider",
    ),
    "FOOD_LICENSE_FILE_RECOGNITION_MODEL": (
        "food_license",
        "file_recognition",
        "model",
    ),
    "FOOD_LICENSE_QWEN_OCR_MODEL": ("food_license", "qwen_ocr", "model"),
    "FOOD_LICENSE_QWEN_OCR_TIMEOUT_SECONDS": (
        "food_license",
        "qwen_ocr",
        "timeout_seconds",
    ),
    "FOOD_LICENSE_QWEN_OCR_MAX_ATTEMPTS": (
        "food_license",
        "qwen_ocr",
        "max_attempts",
    ),
    "FOOD_LICENSE_QWEN_OCR_MAX_PAGES": (
        "food_license",
        "qwen_ocr",
        "max_pages",
    ),
    "FOOD_LICENSE_TEXT_PARSE_MODEL": ("food_license", "text_parse", "model"),
    "FOOD_LICENSE_TEXT_PARSE_TIMEOUT_SECONDS": (
        "food_license",
        "text_parse",
        "timeout_seconds",
    ),
    "FOOD_LICENSE_TEXT_PARSE_MAX_ATTEMPTS": (
        "food_license",
        "text_parse",
        "max_attempts",
    ),
    "FOOD_LICENSE_SKILL_REVIEW_MODEL": ("food_license", "skill_review_model"),
    "FOOD_PRODUCTION_LICENSE_FILE_RECOGNITION_PROVIDER": (
        "food_production_license",
        "file_recognition",
        "provider",
    ),
    "FOOD_PRODUCTION_LICENSE_FILE_RECOGNITION_MODEL": (
        "food_production_license",
        "file_recognition",
        "model",
    ),
    "FOOD_PRODUCTION_LICENSE_QWEN_OCR_MODEL": (
        "food_production_license",
        "qwen_ocr",
        "model",
    ),
    "FOOD_PRODUCTION_LICENSE_QWEN_OCR_TIMEOUT_SECONDS": (
        "food_production_license",
        "qwen_ocr",
        "timeout_seconds",
    ),
    "FOOD_PRODUCTION_LICENSE_QWEN_OCR_MAX_ATTEMPTS": (
        "food_production_license",
        "qwen_ocr",
        "max_attempts",
    ),
    "FOOD_PRODUCTION_LICENSE_QWEN_OCR_MAX_PAGES": (
        "food_production_license",
        "qwen_ocr",
        "max_pages",
    ),
    "FOOD_PRODUCTION_LICENSE_TEXT_PARSE_MODEL": (
        "food_production_license",
        "text_parse",
        "model",
    ),
    "FOOD_PRODUCTION_LICENSE_TEXT_PARSE_TIMEOUT_SECONDS": (
        "food_production_license",
        "text_parse",
        "timeout_seconds",
    ),
    "FOOD_PRODUCTION_LICENSE_TEXT_PARSE_MAX_ATTEMPTS": (
        "food_production_license",
        "text_parse",
        "max_attempts",
    ),
    "FOOD_PRODUCTION_LICENSE_SKILL_REVIEW_MODEL": (
        "food_production_license",
        "skill_review_model",
    ),
    "QC_DOCUMENT_SKILL_REVIEW_MODEL": ("qc_document", "skill_review_model"),
    "ALIYUN_OCR_API_URL": ("aliyun_ocr", "api_url"),
    "ALIYUN_OCR_IMAGE_FIELD": ("aliyun_ocr", "image_field"),
    "ALIYUN_OCR_TIMEOUT_SECONDS": ("aliyun_ocr", "timeout_seconds"),
    "ALIYUN_OCR_BODY_JSON": ("aliyun_ocr", "body_options"),
    "ALIYUN_OCR_LLM_PARSE_MODEL": ("aliyun_ocr", "llm_parse_model"),
    "ALIYUN_OCR_TRY_ROTATIONS": ("aliyun_ocr", "try_rotations"),
    "ALIYUN_OCR_STOP_AFTER_FIRST_LICENSE": (
        "aliyun_ocr",
        "stop_after_first_license",
    ),
    "ALIYUN_OCR_ROTATION_ORDER": ("aliyun_ocr", "rotation_order"),
    "ALIYUN_OCR_LOCAL_PREFILTER_PROVIDER": (
        "aliyun_ocr",
        "local_prefilter_provider",
    ),
    "SRM_MYSQL_HOST": ("srm_mysql", "host"),
    "SRM_MYSQL_PORT": ("srm_mysql", "port"),
    "SRM_MYSQL_DATABASE": ("srm_mysql", "database"),
    "REVIEW_RESULT_MYSQL_HOST": ("review_result_mysql", "host"),
    "REVIEW_RESULT_MYSQL_PORT": ("review_result_mysql", "port"),
    "REVIEW_RESULT_MYSQL_DATABASE": ("review_result_mysql", "database"),
    "STARROCKS_HOST": ("starrocks", "host"),
    "STARROCKS_PORT": ("starrocks", "port"),
    "STARROCKS_DATABASE": ("starrocks", "database"),
    "TOBACCO_CONSISTENCY_DAILY_SYNC_ENABLED": (
        "tobacco_consistency",
        "daily_sync_enabled",
    ),
    "TOBACCO_CONSISTENCY_OA_BUSINESS_LICENSE_FIELD": (
        "tobacco_consistency",
        "oa_business_license_field",
    ),
    "TOBACCO_CONSISTENCY_OA_RELATIONSHIP_EVIDENCE_FIELD": (
        "tobacco_consistency",
        "oa_relationship_evidence_field",
    ),
    "TOBACCO_CONSISTENCY_OA_MULTI_ADDRESS_EVIDENCE_FIELD": (
        "tobacco_consistency",
        "oa_multi_address_evidence_field",
    ),
    "WEB_CONSOLE_AUTH_USERNAME": ("web_console_auth", "username"),
    "WEB_CONSOLE_AUTH_TOKEN_TTL_SECONDS": (
        "web_console_auth",
        "token_ttl_seconds",
    ),
    "WECOM_CORP_ID": ("wecom", "corp_id"),
    "WECOM_AGENT_ID": ("wecom", "agent_id"),
    "WECOM_REDIRECT_URI": ("wecom", "redirect_uri"),
    "WECOM_UNMATCHED_USER_POLICY": ("wecom", "unmatched_user_policy"),
    "WECOM_REVIEWER_USER_IDS": ("wecom", "reviewer_user_ids"),
    "WECOM_ADMIN_USER_IDS": ("wecom", "admin_user_ids"),
    "WECOM_NOTIFICATION_BASE_URL": ("wecom", "notification_base_url"),
    "QWEN_OCR_LOCAL_FILE": ("manual_qwen_ocr", "local_file"),
    "QWEN_OCR_EXPECTED_SUBJECT_NAME": (
        "manual_qwen_ocr",
        "expected_subject_name",
    ),
    "QWEN_OCR_EXPECTED_CREDIT_CODE": (
        "manual_qwen_ocr",
        "expected_credit_code",
    ),
    "QWEN_OCR_SOURCE_SQL": ("manual_qwen_ocr", "source_sql"),
    "QWEN_OCR_VENDOR_NAME": ("manual_qwen_ocr", "vendor_name"),
    "QWEN_OCR_VENDOR_NAME_LIKE": ("manual_qwen_ocr", "vendor_name_like"),
    "QWEN_OCR_SOURCE_OFFSET": ("manual_qwen_ocr", "source_offset"),
}

SECRET_ENV_KEYS = {
    "OPENAI_API_KEY",
    "ALIYUN_OCR_APPCODE",
    "SRM_MYSQL_USER",
    "SRM_MYSQL_PASSWORD",
    "REVIEW_RESULT_MYSQL_USER",
    "REVIEW_RESULT_MYSQL_PASSWORD",
    "STARROCKS_USER",
    "STARROCKS_PASSWORD",
    "WEB_CONSOLE_AUTH_PASSWORD",
    "WEB_CONSOLE_AUTH_SECRET",
    "WECOM_SECRET",
    "WECOM_WORKER_TOKEN",
}

PROJECT_ENV_KEYS = set(CONFIG_KEY_PATHS) | SECRET_ENV_KEYS
CONFIG_FILE_ENV_KEY = "DOCUMENT_AI_REVIEW_CONFIG_FILE"


def load_local_env(project_root: Path | None = None) -> None:
    project_root = project_root or Path(__file__).resolve().parents[3]
    env_values = {
        **load_yaml_config_values(project_root / "app-config" / "app.yaml"),
        **load_yaml_config_values(project_root / "app-config" / "app.local.yaml"),
        **_load_config_file_from_env(),
        **_load_secret_env_values(project_root / ".env"),
        **_load_secret_env_values(project_root / "ai-service" / ".env"),
    }
    for key in PROJECT_ENV_KEYS:
        if key in os.environ:
            continue
        if key in env_values and env_values[key] is not None:
            os.environ[key] = env_values[key] or ""

def _load_config_file_from_env() -> dict[str, str]:
    config_file = os.environ.get(CONFIG_FILE_ENV_KEY, "").strip()
    if not config_file:
        return {}
    return load_yaml_config_values(Path(config_file).expanduser())


def _load_secret_env_values(path: Path) -> dict[str, str]:
    return {
        key: value or ""
        for key, value in dotenv_values(path).items()
        if key in SECRET_ENV_KEYS and value is not None
    }


def load_yaml_config_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} must contain a YAML mapping")

    values = {}
    for env_key, key_path in CONFIG_KEY_PATHS.items():
        value = _get_nested_value(payload, key_path)
        if value is None:
            continue
        values[env_key] = _env_value(value)
    return values


def _get_nested_value(payload: dict[str, Any], key_path: tuple[str, ...]) -> Any:
    value: Any = payload
    for key in key_path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def _env_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


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
