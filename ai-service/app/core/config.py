import os
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel


PROJECT_ENV_KEYS = {
    "OPENAI_API_KEY",
    "OPENAI_API_KEY1",
    "OPENAI_BASE_URL",
    "OPENAI_API_BASE",
    "BUSINESS_LICENSE_VISION_PROVIDER",
    "BUSINESS_LICENSE_VISION_MODEL",
    "SRM_MYSQL_HOST",
    "SRM_MYSQL_PORT",
    "SRM_MYSQL_USER",
    "SRM_MYSQL_PASSWORD",
    "SRM_MYSQL_DATABASE",
}


def load_local_env() -> None:
    project_root = Path(__file__).resolve().parents[3]
    env_values = {
        **dotenv_values(project_root / ".env"),
        **dotenv_values(project_root / "ai-service" / ".env"),
    }
    for key in PROJECT_ENV_KEYS:
        if key in env_values and env_values[key] is not None:
            os.environ[key] = env_values[key] or ""
        else:
            os.environ.pop(key, None)
    if not os.environ.get("OPENAI_API_KEY") and os.environ.get("OPENAI_API_KEY1"):
        os.environ["OPENAI_API_KEY"] = os.environ["OPENAI_API_KEY1"]


load_local_env()


class Settings(BaseModel):
    app_name: str = "document-ai-review ai-service"
    service_name: str = "ai-service"
    api_version: str = "v1"
    timezone: str = "Asia/Shanghai"


settings = Settings()
