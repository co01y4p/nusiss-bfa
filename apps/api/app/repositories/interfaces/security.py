from typing import Any, Protocol

from app.core.models import SecurityEventModel


class SecurityEventRepository(Protocol):
    def record(
        self,
        *,
        event_type: str,
        severity: str = "MEDIUM",
        source_ip: str | None = None,
        input_text: str | None = None,
        details: dict[str, Any] | None = None,
        reason_codes: list[str] | None = None,
    ) -> SecurityEventModel: ...

    def list_events(
        self,
        *,
        severity: str | None = None,
        limit: int = 50,
    ) -> list[SecurityEventModel]: ...
