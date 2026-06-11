import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel


def load_local_env() -> None:
    project_root = Path(__file__).resolve().parents[3]
    load_dotenv(project_root / ".env")
    load_dotenv(project_root / "ai-service" / ".env")
    if not os.environ.get("OPENAI_API_KEY") and os.environ.get("OPENAI_API_KEY1"):
        os.environ["OPENAI_API_KEY"] = os.environ["OPENAI_API_KEY1"]


load_local_env()


class Settings(BaseModel):
    app_name: str = "document-ai-review ai-service"
    service_name: str = "ai-service"
    api_version: str = "v1"
    timezone: str = "Asia/Shanghai"


settings = Settings()
