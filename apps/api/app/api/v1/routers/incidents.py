from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.incidents.models import (
    Incident,
    IncidentCreate,
    IncidentCreated,
    IncidentList,
    IncidentTracked,
    StatusUpdate,
)
from app.repositories.postgres.incidents import SqlAlchemyIncidentRepository
from app.security.authentication import CurrentUser, require_manager
from app.services.incident_service import IncidentService, InvalidStatusTransitionError

router = APIRouter(prefix="/incidents", tags=["incidents"])


def repository(db: Session) -> SqlAlchemyIncidentRepository:
    return SqlAlchemyIncidentRepository(db)


@router.post("", response_model=IncidentCreated, status_code=status.HTTP_201_CREATED)
def create_incident(
    body: IncidentCreate, db: Annotated[Session, Depends(get_db)]
) -> IncidentCreated:
    incident = IncidentService(repository(db)).create(body)
    return IncidentCreated(
        id=incident.id,
        reference_code=incident.reference_code,
        status=incident.status,
    )


@router.get("/track/{reference_code}", response_model=IncidentTracked)
def track_incident(reference_code: str, db: Annotated[Session, Depends(get_db)]) -> IncidentTracked:
    incident = repository(db).get_by_reference(reference_code)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return IncidentTracked(
        reference_code=incident.reference_code,
        status=incident.status,
        location=incident.location,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
    )


@router.get("", response_model=IncidentList)
def list_incidents(
    db: Annotated[Session, Depends(get_db)],
    manager: Annotated[CurrentUser, Depends(require_manager)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> IncidentList:
    del manager
    return IncidentList(incidents=repository(db).list_recent(limit=limit, offset=offset))


@router.patch("/{incident_id}/status", response_model=Incident)
def update_incident_status(
    incident_id: str,
    body: StatusUpdate,
    db: Annotated[Session, Depends(get_db)],
    manager: Annotated[CurrentUser, Depends(require_manager)],
) -> Incident:
    del manager
    try:
        incident = IncidentService(repository(db)).update_status(incident_id, body.status.value)
    except InvalidStatusTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return incident
