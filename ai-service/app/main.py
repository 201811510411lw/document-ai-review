from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.auth import router as auth_router
from app.api.business_license_reviews import router as business_license_reviews_router
from app.api.food_license_reviews import router as food_license_reviews_router
from app.api.health import router as health_router
from app.api.tobacco_license_sources import router as tobacco_license_sources_router
from app.api.tobacco_license_consistency import router as tobacco_license_consistency_router
from app.api.wecom_frontend import api_router as wecom_frontend_api_router
from app.api.wecom_frontend import auth_router as wecom_frontend_auth_router
from app.api.qc_reviews import router as qc_reviews_router
from app.api.wecom_notifications import router as wecom_notifications_router
from app.core.config import settings
from app.integrations.mysql_client import mysql_settings_from_env
from app.repositories import build_review_result_repository_from_env
from app.services.review_service import ReviewService
from app.services.scheduled_review_service import DailyReviewScheduler


app = FastAPI(
    title=settings.app_name,
    version=settings.api_version,
)

_scheduler: DailyReviewScheduler | None = None


@app.on_event("startup")
def start_scheduler():
    global _scheduler
    try:
        source_settings = mysql_settings_from_env("STARROCKS")
        review_db_settings = mysql_settings_from_env("REVIEW_RESULT_MYSQL")
        _scheduler = DailyReviewScheduler(
            source_settings=source_settings,
            review_db_settings=review_db_settings,
        )
        _scheduler.start()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("定时调度器启动失败（不影响 API）: %s", e)


@app.on_event("shutdown")
def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.stop()
        _scheduler = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://0.0.0.0:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(wecom_frontend_auth_router)
app.include_router(business_license_reviews_router)
app.include_router(food_license_reviews_router)
app.include_router(qc_reviews_router)
app.include_router(tobacco_license_sources_router)
app.include_router(tobacco_license_consistency_router)
app.include_router(wecom_frontend_api_router)
app.include_router(wecom_notifications_router)


class WebConsoleStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope) -> FileResponse:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as error:
            if error.status_code != 404 or not _should_fallback_to_web_console(path):
                raise
            return FileResponse(Path(self.directory) / "index.html")


def _should_fallback_to_web_console(path: str) -> bool:
    if path == "api" or path.startswith("api/"):
        return False
    return Path(path).suffix == ""


_web_dist = Path(__file__).resolve().parents[2] / "web-console" / "dist"
if _web_dist.exists():
    app.mount("/", WebConsoleStaticFiles(directory=_web_dist, html=True), name="web-console")
