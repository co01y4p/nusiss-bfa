import re
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.monitoring.metrics import record_http_request

# Regex to normalize path segments containing UUIDs or BFA reference codes
UUID_PATTERN = re.compile(
    r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)
BFA_CODE_PATTERN = re.compile(r"/BFA-[A-Z0-9]{6,12}", re.IGNORECASE)
NUMERIC_ID_PATTERN = re.compile(r"/\d+")


def normalize_metric_path(path: str) -> str:
    """Strip variable identifiers from URL paths to keep metric cardinality low."""
    normalized = UUID_PATTERN.sub("/{id}", path)
    normalized = BFA_CODE_PATTERN.sub("/{reference_code}", normalized)
    normalized = NUMERIC_ID_PATTERN.sub("/{id}", normalized)
    return normalized


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Don't track /metrics itself to prevent self-observability loops
        if request.url.path == "/metrics":
            return await call_next(request)

        start_time = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - start_time
            normalized_path = normalize_metric_path(request.url.path)
            record_http_request(
                method=request.method,
                path=normalized_path,
                status_code=status_code,
                duration_seconds=duration,
            )
