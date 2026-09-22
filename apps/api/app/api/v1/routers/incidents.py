from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.domain.incidents.models import (
    Incident,
    IncidentCreate,
    IncidentCreated,
    IncidentList,
    IncidentTracked,
    StatusUpdate,
    TriageUpdate,
)
from app.rag.embeddings import EmbeddingProvider, FakeEmbeddings, OpenAICompatibleEmbeddings
from app.repositories.postgres.incidents import SqlAlchemyIncidentRepository
from app.security.authentication import CurrentUser, require_manager
from app.services.incident_service import IncidentService, InvalidStatusTransitionError

router = APIRouter(prefix="/incidents", tags=["incidents"])


def repository(db: Session) -> SqlAlchemyIncidentRepository:
    return SqlAlchemyIncidentRepository(db)


def get_embeddings(settings: Settings) -> EmbeddingProvider:
    has_keys = bool(settings.llm_base_url and settings.llm_api_key)
    if settings.llm_provider in {"openai", "openrouter"} and has_keys:
        return OpenAICompatibleEmbeddings(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.embedding_model,
        )
    return FakeEmbeddings(dim=settings.embedding_dim)


@router.post("", response_model=IncidentCreated, status_code=status.HTTP_201_CREATED)
async def create_incident(
    body: IncidentCreate,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> IncidentCreated:
    embeddings = get_embeddings(settings)
    incident = await IncidentService(repository(db), embeddings).create(body)
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
    requires_review: Annotated[bool | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    priority: Annotated[str | None, Query()] = None,
) -> IncidentList:
    del manager
    return IncidentList(
        incidents=repository(db).list_recent(
            limit=limit,
            offset=offset,
            requires_human_review=requires_review,
            status=status_filter,
            priority=priority,
        )
    )


@router.patch("/{incident_id}/status", response_model=Incident)
def update_incident_status(
    incident_id: str,
    body: StatusUpdate,
    db: Annotated[Session, Depends(get_db)],
    manager: Annotated[CurrentUser, Depends(require_manager)],
) -> Incident:
    del manager
    try:
        incident = IncidentService(repository(db)).update_status(
            incident_id, body.status.value, reason=body.reason
        )
    except InvalidStatusTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return incident


@router.patch("/{incident_id}/triage", response_model=Incident)
def update_incident_triage(
    incident_id: str,
    body: TriageUpdate,
    db: Annotated[Session, Depends(get_db)],
    manager: Annotated[CurrentUser, Depends(require_manager)],
) -> Incident:
    del manager
    incident = IncidentService(repository(db)).update_triage(
        incident_id,
        category=body.category,
        priority=body.priority,
        assigned_team=body.assigned_team,
        location=body.location,
        requires_human_review=body.requires_human_review,
        reason=body.reason,
    )
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return incident
