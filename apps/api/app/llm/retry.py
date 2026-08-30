import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

T = TypeVar("T")


async def with_transient_retries(  # noqa: UP047
    operation: Callable[[], Awaitable[T]], *, retries: int = 2, base_delay_seconds: float = 0.1
) -> T:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return await operation()
        except (TimeoutError, ConnectionError, httpx.TransportError) as exc:
            last_error = exc
            if attempt < retries:
                await asyncio.sleep(base_delay_seconds * (2**attempt))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in {408, 409, 429} and exc.response.status_code < 500:
                raise
            last_error = exc
            if attempt < retries:
                await asyncio.sleep(base_delay_seconds * (2**attempt))
    assert last_error is not None
    raise last_error
