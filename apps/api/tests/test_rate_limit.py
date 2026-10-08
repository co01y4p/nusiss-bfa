from ipaddress import ip_network
from typing import Any

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import Settings
from app.middleware.rate_limit import (
    FallbackRateLimiter,
    InMemoryRateLimiter,
    RateLimitDecision,
    RateLimitMiddleware,
    ValkeyRateLimiter,
    build_rate_limiter,
)


def valkey_limiter(server: fakeredis.FakeServer) -> ValkeyRateLimiter:
    return ValkeyRateLimiter(client=fakeredis.FakeAsyncRedis(server=server))


@pytest.mark.asyncio
async def test_valkey_limiter_allows_the_limit_then_blocks_with_retry_after() -> None:
    limiter = valkey_limiter(fakeredis.FakeServer())

    decisions = [await limiter.check("rl:test", 3, 60) for _ in range(5)]

    assert [d.limited for d in decisions] == [False, False, False, True, True]
    assert all(d.backend == "valkey" for d in decisions)
    assert 1 <= decisions[3].retry_after <= 60


@pytest.mark.asyncio
async def test_rejected_requests_do_not_extend_the_lockout() -> None:
    server = fakeredis.FakeServer()
    limiter = valkey_limiter(server)
    for _ in range(3):
        await limiter.check("rl:test", 3, 60)
    for _ in range(10):
        await limiter.check("rl:test", 3, 60)

    client = fakeredis.FakeAsyncRedis(server=server)
    assert await client.zcard("rl:test") == 3


@pytest.mark.asyncio
async def test_two_api_processes_share_one_limit_through_valkey() -> None:
    server = fakeredis.FakeServer()
    process_a, process_b = valkey_limiter(server), valkey_limiter(server)

    allowed = [(await process_a.check("rl:shared", 4, 60)).limited for _ in range(2)]
    allowed += [(await process_b.check("rl:shared", 4, 60)).limited for _ in range(3)]

    assert allowed == [False, False, False, False, True]


@pytest.mark.asyncio
async def test_the_in_memory_limiter_does_not_share_between_processes() -> None:
    first, second = InMemoryRateLimiter(), InMemoryRateLimiter()
    for _ in range(4):
        assert not (await first.check("rl:shared", 4, 60)).limited

    # The behaviour Valkey fixes: a second process starts from zero.
    assert not (await second.check("rl:shared", 4, 60)).limited


class BrokenLimiter:
    def __init__(self) -> None:
        self.calls = 0

    async def check(self, key: str, max_requests: int, window_seconds: int) -> RateLimitDecision:
        del key, max_requests, window_seconds
        self.calls += 1
        raise RedisConnectionError("valkey is down")


@pytest.mark.asyncio
async def test_valkey_outage_falls_back_to_memory_and_stops_retrying_during_cooldown() -> None:
    broken = BrokenLimiter()
    limiter = FallbackRateLimiter(broken, InMemoryRateLimiter(), cooldown_seconds=30)

    decisions = [await limiter.check("rl:test", 2, 60) for _ in range(4)]

    assert [d.limited for d in decisions] == [False, False, True, True]
    assert {d.backend for d in decisions} == {"memory"}
    assert broken.calls == 1  # one failed attempt, then skipped for the cooldown


@pytest.mark.asyncio
async def test_unreachable_valkey_url_never_raises() -> None:
    limiter = build_rate_limiter("valkey", "redis://127.0.0.1:1/0")

    decision = await limiter.check("rl:test", 5, 60)

    assert decision.limited is False
    assert decision.backend == "memory"


def test_build_rate_limiter_memory_backend() -> None:
    assert isinstance(build_rate_limiter("memory", "redis://unused"), InMemoryRateLimiter)


def make_client(
    limiter: Any,
    *,
    trusted: list[str] | None = None,
    peer: tuple[str, int] = ("testclient", 50000),
    max_requests: int = 2,
) -> TestClient:
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        max_requests_per_minute=max_requests,
        window_seconds=60,
        limiter=limiter,
        trusted_proxies=[ip_network(item) for item in trusted or []],
    )

    @app.post("/api/v1/assistant/messages")
    def messages() -> dict[str, str]:
        return {"ok": "yes"}

    return TestClient(app, client=peer)


def test_middleware_returns_429_with_retry_after_from_valkey() -> None:
    client = make_client(valkey_limiter(fakeredis.FakeServer()))

    statuses = [client.post("/api/v1/assistant/messages").status_code for _ in range(3)]
    blocked = client.post("/api/v1/assistant/messages")

    assert statuses == [200, 200, 429]
    assert int(blocked.headers["Retry-After"]) >= 1
    assert blocked.json()["reason_code"] == "RATE_LIMIT_EXCEEDED"


def test_untrusted_client_cannot_dodge_the_limit_by_spoofing_forwarded_for() -> None:
    client = make_client(InMemoryRateLimiter(), peer=("203.0.113.9", 50000))

    statuses = [
        client.post("/api/v1/assistant/messages", headers={"X-Forwarded-For": f"198.51.100.{i}"})
        for i in range(3)
    ]

    assert [r.status_code for r in statuses] == [200, 200, 429]


def test_trusted_proxy_forwarded_for_identifies_each_real_client() -> None:
    client = make_client(InMemoryRateLimiter(), trusted=["10.0.0.0/8"], peer=("10.1.2.3", 50000))
    post = client.post

    first_user = [
        post("/api/v1/assistant/messages", headers={"X-Forwarded-For": "198.51.100.1"}).status_code
        for _ in range(3)
    ]
    second_user = post(
        "/api/v1/assistant/messages", headers={"X-Forwarded-For": "198.51.100.2"}
    ).status_code

    assert first_user == [200, 200, 429]
    assert second_user == 200  # a different real client is not limited by the first one


def test_trusted_proxy_networks_setting_parses_and_rejects_bad_values() -> None:
    settings = Settings(trusted_proxy_ips="10.0.0.0/8, 192.168.1.5")
    assert [str(n) for n in settings.trusted_proxy_networks] == ["10.0.0.0/8", "192.168.1.5/32"]
    assert Settings(trusted_proxy_ips="").trusted_proxy_networks == []
    with pytest.raises(ValueError):
        _ = Settings(trusted_proxy_ips="not-an-ip").trusted_proxy_networks
