from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from app.domain.incidents.models import IncidentCreate
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


class FindRecentIncidentsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str = Field(min_length=1, max_length=200)
    lookback_hours: int = Field(default=72, ge=1, le=720)
    limit: int = Field(default=5, ge=1, le=20)
    exclude_incident_id: str | None = None


def register_incident_tools(registry: "ToolRegistry", incident_repo: IncidentRepository) -> None:
    def create_incident(args: CreateIncidentInput) -> dict[str, str]:
        incident = IncidentService(incident_repo).create(
            IncidentCreate(description=args.description, location=args.location)
        )
        return {
            "id": incident.id,
            "reference_code": incident.reference_code,
            "status": (
                incident.status.value
                if hasattr(incident.status, "value")
                else str(incident.status)
            ),
        }

    registry.register(
        name="create_incident",
        description="Create and persist a new facility incident",
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
        updated = incident_repo.update_status(args.incident_id, args.status)
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

    def find_recent_incidents(args: FindRecentIncidentsInput) -> list[dict[str, str | None]]:
        since = datetime.now(UTC) - timedelta(hours=args.lookback_hours)
        matches = incident_repo.find_similar(
            location=args.location,
            since=since,
            exclude_id=args.exclude_incident_id,
            limit=args.limit,
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
                "created_at": incident.created_at.isoformat(),
            }
            for incident in matches
        ]

    registry.register(
        name="find_recent_incidents",
        description=(
            "Find recent incidents reported at a similar location, for pattern/duplicate "
            "context. Internal workflow use only, not exposed to end users."
        ),
        input_schema=FindRecentIncidentsInput,
        required_role="SYSTEM",
        handler=find_recent_incidents,
    )
