from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.api_version,
        "timestamp": datetime.now(ZoneInfo(settings.timezone)).isoformat(),
    }
