from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import SecurityEventModel
from app.repositories.interfaces.security import SecurityEventRepository


class PostgresSecurityEventRepository(SecurityEventRepository):
    def __init__(self, db: Session) -> None:
        self.db = db

    def record(
        self,
        *,
        event_type: str,
        severity: str = "MEDIUM",
        source_ip: str | None = None,
        input_text: str | None = None,
        details: dict[str, Any] | None = None,
        reason_codes: list[str] | None = None,
    ) -> SecurityEventModel:
        event = SecurityEventModel(
            event_type=event_type,
            severity=severity,
            source_ip=source_ip,
            input_text=input_text,
            details=details or {},
            reason_codes=reason_codes or [],
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def list_events(
        self,
        *,
        severity: str | None = None,
        limit: int = 50,
    ) -> list[SecurityEventModel]:
        stmt = select(SecurityEventModel)
        if severity:
            stmt = stmt.where(SecurityEventModel.severity == severity.upper())
        stmt = stmt.order_by(SecurityEventModel.created_at.desc()).limit(limit)
        return list(self.db.scalars(stmt).all())
