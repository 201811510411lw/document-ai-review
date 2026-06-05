from fastapi import FastAPI

from app.api.food_license import router as food_license_router

app = FastAPI(title="Document AI Review Service", version="0.1.0")


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "ai-service"}


app.include_router(food_license_router, prefix="/api/v1")
