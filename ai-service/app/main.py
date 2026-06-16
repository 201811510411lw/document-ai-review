from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.auth import router as auth_router
from app.api.business_license_reviews import router as business_license_reviews_router
from app.api.food_license_reviews import router as food_license_reviews_router
from app.api.health import router as health_router
from app.api.qc_reviews import router as qc_reviews_router
from app.api.wecom_notifications import router as wecom_notifications_router
from app.core.config import settings


app = FastAPI(
    title=settings.app_name,
    version=settings.api_version,
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(business_license_reviews_router)
app.include_router(food_license_reviews_router)
app.include_router(qc_reviews_router)
app.include_router(wecom_notifications_router)


_web_dist = Path(__file__).resolve().parents[2] / "web-console" / "dist"
if _web_dist.exists():
    app.mount("/", StaticFiles(directory=_web_dist, html=True), name="web-console")
