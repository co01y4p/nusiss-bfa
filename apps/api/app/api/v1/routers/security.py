from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.incidents.models import SecurityEvent, SecurityEventList
from app.repositories.postgres.security_events import PostgresSecurityEventRepository
from app.security.authentication import CurrentUser, require_manager

router = APIRouter(prefix="/security", tags=["security"])


@router.get("/events", response_model=SecurityEventList)
def list_security_events(
    db: Annotated[Session, Depends(get_db)],
    manager: Annotated[CurrentUser, Depends(require_manager)],
    severity: Annotated[str | None, Query(pattern=r"^(HIGH|MEDIUM|LOW)$")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> SecurityEventList:
    del manager
    repo = PostgresSecurityEventRepository(db)
    rows = repo.list_events(severity=severity, limit=limit)
    return SecurityEventList(
        events=[
            SecurityEvent(
                id=row.id,
                event_type=row.event_type,
                severity=row.severity,
                source_ip=row.source_ip,
                input_text=row.input_text,
                details=row.details if isinstance(row.details, dict) else {},
                reason_codes=row.reason_codes if isinstance(row.reason_codes, list) else [],
                created_at=row.created_at,
            )
            for row in rows
        ]
    )
