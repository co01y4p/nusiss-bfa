from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.middleware.metrics import PrometheusMetricsMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.monitoring.logging import setup_logging
from app.monitoring.metrics import generate_metrics_exposition


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    del app
    settings = get_settings()
    setup_logging(json_format=settings.app_env != "test")
    if settings.app_env == "production" and len(settings.jwt_secret) < 32:
        raise RuntimeError("JWT_SECRET must contain at least 32 characters in production")
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(PrometheusMetricsMiddleware)
app.add_middleware(
    RateLimitMiddleware,
    max_requests_per_minute=settings.rate_limit_requests_per_minute,
    window_seconds=settings.rate_limit_window_seconds,
    enabled=settings.rate_limit_enabled,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(api_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs"}


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    content, media_type = generate_metrics_exposition()
    return Response(content=content, media_type=media_type)
