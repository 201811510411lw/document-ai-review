from fastapi import FastAPI

from app.api.business_license_reviews import router as business_license_reviews_router
from app.api.food_license_reviews import router as food_license_reviews_router
from app.api.health import router as health_router
from app.core.config import settings


app = FastAPI(
    title=settings.app_name,
    version=settings.api_version,
)

app.include_router(health_router)
app.include_router(business_license_reviews_router)
app.include_router(food_license_reviews_router)
