from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from app.domain.incidents.models import IncidentCreate
from app.domain.incidents.policies import is_unspecified_location
from app.rag.embeddings import EmbeddingProvider
from app.repositories.interfaces.incidents import IncidentRepository
from app.services.incident_service import IncidentService

if TYPE_CHECKING:
    from app.tools.registry import ToolRegistry


class LookupIncidentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_code: str = Field(min_length=1, max_length=64)


class CreateIncidentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=4000)
    location: str = Field(min_length=1, max_length=200)


class UpdateIncidentStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str
    status: str
    reason: str = Field(
        default="Manager tool override",
        description="Mandatory operational reason for the status transition",
    )


class FindRecentIncidentsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str = Field(min_length=1, max_length=200)
    lookback_hours: int = Field(default=72, ge=1, le=720)
    limit: int = Field(default=5, ge=1, le=20)
    exclude_incident_id: str | None = None


def register_incident_tools(
    registry: "ToolRegistry",
    incident_repo: IncidentRepository,
    embeddings: EmbeddingProvider,
    *,
    similarity_threshold: float = 0.75,
) -> None:
    async def create_incident(args: CreateIncidentInput) -> dict[str, str]:
        incident = await IncidentService(incident_repo, embeddings).create(
            IncidentCreate(description=args.description, location=args.location)
        )
        return {
            "id": incident.id,
            "reference_code": incident.reference_code,
            "status": (
                incident.status.value if hasattr(incident.status, "value") else str(incident.status)
            ),
        }

    registry.register(
        name="create_incident",
        description=(
            "Create and persist a new facility incident. Call exactly once only after "
            "classifying the current occupant message as INCIDENT_REPORT."
        ),
        input_schema=CreateIncidentInput,
        required_role="SYSTEM",
        handler=create_incident,
    )

    def lookup_incident(args: LookupIncidentInput) -> dict[str, str | None] | None:
        incident = incident_repo.get_by_reference(args.reference_code)
        if not incident:
            return None
        return {
            "reference_code": incident.reference_code,
            "status": (
                incident.status.value if hasattr(incident.status, "value") else str(incident.status)
            ),
            "category": incident.category,
            "priority": incident.priority,
            "location": incident.location,
        }

    def update_status(args: UpdateIncidentStatusInput) -> dict[str, str] | None:
        updated = incident_repo.update_status(args.incident_id, args.status, reason=args.reason)
        if not updated:
            return None
        return {
            "id": updated.id,
            "status": (
                updated.status.value if hasattr(updated.status, "value") else str(updated.status)
            ),
        }

    registry.register(
        name="lookup_incident_status",
        description="Lookup public status of an incident using opaque reference code",
        input_schema=LookupIncidentInput,
        required_role="PUBLIC",
        handler=lookup_incident,
    )

    registry.register(
        name="update_incident_status",
        description="Update status of an incident (restricted to facility managers)",
        input_schema=UpdateIncidentStatusInput,
        required_role="MANAGER",
        handler=update_status,
    )

    async def find_recent_incidents(
        args: FindRecentIncidentsInput,
    ) -> list[dict[str, str | None]]:
        if is_unspecified_location(args.location):
            return []
        since = datetime.now(UTC) - timedelta(hours=args.lookback_hours)
        location_embedding = await embeddings.embed_query(args.location)
        matches = incident_repo.find_similar(
            location_embedding=location_embedding,
            since=since,
            exclude_id=args.exclude_incident_id,
            limit=args.limit,
            similarity_threshold=similarity_threshold,
        )
        return [
            {
                "reference_code": incident.reference_code,
                "location": incident.location,
                "category": incident.category,
                "priority": incident.priority,
                "status": (
                    incident.status.value
                    if hasattr(incident.status, "value")
                    else str(incident.status)
                ),
                "assigned_team": incident.assigned_team,
                "override_reason": incident.override_reason,
                "created_at": incident.created_at.isoformat(),
            }
            for incident in matches
        ]

    registry.register(
        name="find_recent_incidents",
        description=(
            "Find recent incidents at a semantically similar location (embedding search, not "
            "exact text match — e.g. 'Level 4 Room 402' and 'Level 4 Room 404' can both match), "
            "for pattern/duplicate context. Internal workflow use only, not exposed to end users."
        ),
        input_schema=FindRecentIncidentsInput,
        required_role="SYSTEM",
        handler=find_recent_incidents,
    )
