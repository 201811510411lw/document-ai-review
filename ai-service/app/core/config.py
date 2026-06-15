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
    "BUSINESS_LICENSE_VISION_MODEL",
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


settings = Settings()
