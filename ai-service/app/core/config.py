import os

from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "document-ai-review ai-service"
    service_name: str = "ai-service"
    api_version: str = "v1"
    timezone: str = "Asia/Shanghai"

    @property
    def food_license_llm_enabled(self) -> bool:
        return os.getenv("FOOD_LICENSE_LLM_ENABLED", "false").lower() == "true"

    @property
    def food_license_llm_provider(self) -> str:
        return os.getenv("FOOD_LICENSE_LLM_PROVIDER", "compatible")

    @property
    def food_license_llm_model(self) -> str:
        return os.getenv("FOOD_LICENSE_LLM_MODEL", "")

    @property
    def food_license_llm_base_url(self) -> str:
        return os.getenv("FOOD_LICENSE_LLM_BASE_URL", "")

    @property
    def food_license_llm_api_key(self) -> str:
        return os.getenv("FOOD_LICENSE_LLM_API_KEY", "")


settings = Settings()
