import ipaddress
import logging
import math
import time
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, Protocol

import redis.asyncio as redis
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from app.monitoring.metrics import record_rate_limit_decision

logger = logging.getLogger("app.middleware.rate_limit")

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


@dataclass(frozen=True)
class RateLimitDecision:
    limited: bool
    retry_after: int
    backend: str


class RateLimiter(Protocol):
    async def check(
        self, key: str, max_requests: int, window_seconds: int
    ) -> RateLimitDecision: ...


class InMemoryRateLimiter:
    """Sliding-window in-memory rate limiter.

    Per process: with several API processes each one allows the full limit, which is why
    Valkey is the default backend. This remains the fallback when Valkey is unreachable.
    """

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

    async def check(self, key: str, max_requests: int, window_seconds: int) -> RateLimitDecision:
        limited, retry_after = self.is_rate_limited(key, max_requests, window_seconds)
        return RateLimitDecision(limited=limited, retry_after=retry_after, backend="memory")


class ValkeyRateLimiter:
    """Sliding-window limiter shared by every API process, stored in a Valkey sorted set.

    Each request adds one member scored by its timestamp. The whole step (trim, add,
    count) runs in one MULTI/EXEC transaction. A request that pushes the count over the
    limit removes its own member again, so rejected requests never extend a lockout.
    Timestamps come from the API host clock; skew between replicas is a few milliseconds
    under NTP, which is negligible against a 60-second window.
    """

    def __init__(
        self,
        url: str = "",
        *,
        client: "redis.Redis | None" = None,
        socket_timeout: float = 1.0,
    ) -> None:
        self._url = url
        self._socket_timeout = socket_timeout
        self._client = client

    def _get_client(self) -> "redis.Redis":
        if self._client is None:
            self._client = redis.from_url(  # type: ignore[no-untyped-call]
                self._url,
                socket_connect_timeout=self._socket_timeout,
                socket_timeout=self._socket_timeout,
            )
        return self._client

    async def check(self, key: str, max_requests: int, window_seconds: int) -> RateLimitDecision:
        client = self._get_client()
        now_ms = int(time.time() * 1000)
        window_ms = window_seconds * 1000
        member = f"{now_ms}-{uuid.uuid4().hex}"

        async with client.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, now_ms - window_ms)
            pipe.zadd(key, {member: now_ms})
            pipe.zcard(key)
            pipe.zrange(key, 0, 0, withscores=True)
            pipe.pexpire(key, window_ms)
            results = await pipe.execute()

        count = int(results[2])
        if count <= max_requests:
            return RateLimitDecision(limited=False, retry_after=0, backend="valkey")

        await client.zrem(key, member)
        oldest_ms = results[3][0][1] if results[3] else now_ms
        retry_after = max(1, math.ceil((oldest_ms + window_ms - now_ms) / 1000))
        return RateLimitDecision(limited=True, retry_after=retry_after, backend="valkey")

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()


class FallbackRateLimiter:
    """Use the primary limiter; if it fails, use the fallback and retry later.

    Rate limiting must never take the API down. After a failure the primary is skipped
    for `cooldown_seconds`, so a dead Valkey does not add a connection timeout to every
    request.
    """

    def __init__(
        self,
        primary: RateLimiter,
        fallback: RateLimiter,
        *,
        cooldown_seconds: float = 30.0,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._cooldown_seconds = cooldown_seconds
        self._skip_until = 0.0

    async def check(self, key: str, max_requests: int, window_seconds: int) -> RateLimitDecision:
        now = time.monotonic()
        if now >= self._skip_until:
            try:
                decision = await self._primary.check(key, max_requests, window_seconds)
                if self._skip_until:
                    logger.info("Rate limiter backend recovered; using it again")
                    self._skip_until = 0.0
                return decision
            except Exception as exc:
                self._skip_until = now + self._cooldown_seconds
                logger.warning(
                    "Rate limiter backend unavailable (%r); using in-memory limits for %.0fs",
                    exc,
                    self._cooldown_seconds,
                )
        return await self._fallback.check(key, max_requests, window_seconds)


def build_rate_limiter(backend: str, valkey_url: str) -> RateLimiter:
    if backend == "valkey":
        return FallbackRateLimiter(ValkeyRateLimiter(valkey_url), InMemoryRateLimiter())
    return InMemoryRateLimiter()


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
        limiter: RateLimiter | None = None,
        trusted_proxies: Sequence[IPNetwork] = (),
    ) -> None:
        super().__init__(app)
        self.max_requests = max_requests_per_minute
        self.window_seconds = window_seconds
        self.enabled = enabled
        self.limiter: RateLimiter = limiter or InMemoryRateLimiter()
        self.trusted_proxies = tuple(trusted_proxies)

    def _is_trusted_proxy(self, peer: str) -> bool:
        try:
            address = ipaddress.ip_address(peer)
        except ValueError:
            return False
        return any(address in network for network in self.trusted_proxies)

    def _client_ip(self, request: Request) -> str:
        peer = request.client.host if request.client else "unknown_client"
        forwarded_for = request.headers.get("X-Forwarded-For")
        # Anyone can send this header, so honour it only when the connection really
        # comes from a configured reverse proxy. Otherwise a client could change it on
        # every request and never be limited.
        if forwarded_for and self._is_trusted_proxy(peer):
            return forwarded_for.split(",")[0].strip() or peer
        return peer

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self.enabled:
            return await call_next(request)

        path = request.url.path.rstrip("/")
        is_targeted_path = any(
            path == target or path.startswith(target + "/") for target in self.RATE_LIMITED_PATHS
        )
        if not is_targeted_path:
            return await call_next(request)

        key = f"rl:{path}:{self._client_ip(request)}"
        decision = await self.limiter.check(
            key, max_requests=self.max_requests, window_seconds=self.window_seconds
        )
        record_rate_limit_decision(decision.backend, "limited" if decision.limited else "allowed")

        if decision.limited:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Too many requests. Please slow down.",
                    "retry_after_seconds": decision.retry_after,
                    "reason_code": "RATE_LIMIT_EXCEEDED",
                },
                headers={"Retry-After": str(decision.retry_after)},
            )

        return await call_next(request)
