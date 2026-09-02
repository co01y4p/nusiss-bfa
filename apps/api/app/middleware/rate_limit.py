import time
from collections import defaultdict
from typing import ClassVar

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse
from starlette.types import ASGIApp


class InMemoryRateLimiter:
    """Sliding-window in-memory rate limiter fallback."""

    def __init__(self) -> None:
        self._history: dict[str, list[float]] = defaultdict(list)

    def is_rate_limited(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int]:
        now = time.time()
        window_start = now - window_seconds
        records = [ts for ts in self._history[key] if ts > window_start]
        self._history[key] = records

        if len(records) >= max_requests:
            oldest = records[0]
            retry_after = max(1, int(oldest + window_seconds - now))
            return True, retry_after

        self._history[key].append(now)
        return False, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limits public endpoints by client IP address."""

    RATE_LIMITED_PATHS: ClassVar[set[str]] = {
        "/api/v1/incidents",
        "/api/v1/assistant",
        "/api/v1/assistant/chat",
        "/api/v1/knowledge/search",
        "/api/v1/auth/login",
    }

    def __init__(
        self,
        app: ASGIApp,
        max_requests_per_minute: int = 60,
        window_seconds: int = 60,
        enabled: bool = True,
    ) -> None:
        super().__init__(app)
        self.max_requests = max_requests_per_minute
        self.window_seconds = window_seconds
        self.enabled = enabled
        self.limiter = InMemoryRateLimiter()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self.enabled:
            return await call_next(request)

        path = request.url.path.rstrip("/")
        is_targeted_path = any(
            path == target or path.startswith(target + "/") for target in self.RATE_LIMITED_PATHS
        )
        if not is_targeted_path:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown_client"
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()

        key = f"rl:{path}:{client_ip}"
        limited, retry_after = self.limiter.is_rate_limited(
            key, max_requests=self.max_requests, window_seconds=self.window_seconds
        )

        if limited:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Too many requests. Please slow down.",
                    "retry_after_seconds": retry_after,
                    "reason_code": "RATE_LIMIT_EXCEEDED",
                },
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
