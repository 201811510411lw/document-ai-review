import logging
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
from app.api.rpa_verification import router as rpa_verification_router
from app.core.config import settings
from app.integrations.mysql_client import mysql_settings_from_env
from app.repositories import build_review_result_repository_from_env
from app.services.review_service import ReviewService
from app.services.scheduled_review_service import DailyReviewScheduler
from app.services.oa_auto_review_callback import HttpOaAutoReviewCallbackClient
from app.services.oa_review_recovery import OaReviewRecoveryScheduler


# Uvicorn 默认只显示 WARNING；OA 审核阶段日志需要以 INFO 级别输出。
logging.getLogger("app").setLevel(logging.INFO)


app = FastAPI(
    title=settings.app_name,
    version=settings.api_version,
)

_scheduler: DailyReviewScheduler | None = None
_oa_recovery_scheduler: OaReviewRecoveryScheduler | None = None


@app.on_event("startup")
def start_scheduler():
    global _scheduler, _oa_recovery_scheduler
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
    try:
        recovery_repository = build_review_result_repository_from_env()
        callback_client = HttpOaAutoReviewCallbackClient(settings.oa_auto_review_callback_url)
        _oa_recovery_scheduler = OaReviewRecoveryScheduler(recovery_repository, callback_client)
        _oa_recovery_scheduler.start()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("OA 恢复调度器启动失败（不影响 API）: %s", e)


@app.on_event("shutdown")
def stop_scheduler():
    global _scheduler, _oa_recovery_scheduler
    if _oa_recovery_scheduler:
        _oa_recovery_scheduler.stop()
        _oa_recovery_scheduler = None
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
app.include_router(rpa_verification_router)


class WebConsoleStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope) -> FileResponse:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as error:
            if error.status_code != 404 or not _should_fallback_to_web_console(path):
                raise
            return FileResponse(Path(self.directory) / "index.html")


def _should_fallback_to_web_console(path: str) -> bool:
    # path 可能带也可能不带前导斜杠，取决于 Starlette 版本
    # 统一去掉前导 / 再做判断
    stripped = path.lstrip("/")
    # 以 api/ 开头的路径都是后端 API，不交由前端 SPA 路由处理
    if stripped.startswith("api") and (len(stripped) == 3 or stripped.startswith("api/")):
        return False
    # 有文件扩展名的（.js, .css, .png 等）不回退
    if Path(path).suffix:
        return False
    # 无扩展名且非 API 路径 → SPA 前端路由，回退到 index.html
    return True


_web_dist = Path(__file__).resolve().parents[2] / "web-console" / "dist"
if _web_dist.exists():
    app.mount("/", WebConsoleStaticFiles(directory=_web_dist, html=True), name="web-console")
