from app.domain.incidents.models import Incident, IncidentCreate
from app.domain.incidents.policies import can_transition_status
from app.repositories.interfaces.incidents import IncidentRepository


class InvalidStatusTransitionError(ValueError):
    pass


class IncidentService:
    def __init__(self, repository: IncidentRepository) -> None:
        self.repository = repository

    def create(self, data: IncidentCreate) -> Incident:
        return self.repository.create(description=data.description, location=data.location)

    def update_status(
        self, incident_id: str, target_status: str, *, reason: str
    ) -> Incident | None:
        incident = self.repository.get_by_id(incident_id)
        if incident is None:
            return None
        if not can_transition_status(incident.status.value, target_status):
            raise InvalidStatusTransitionError(
                f"Cannot transition from {incident.status.value} to {target_status}"
            )
        return self.repository.update_status(incident_id, target_status, reason=reason)

    def update_triage(
        self,
        incident_id: str,
        *,
        category: str | None = None,
        priority: str | None = None,
        assigned_team: str | None = None,
        location: str | None = None,
        requires_human_review: bool | None = None,
        reason: str,
    ) -> Incident | None:
        incident = self.repository.get_by_id(incident_id)
        if incident is None:
            return None
        return self.repository.update_triage(
            incident_id,
            location=location if location is not None else incident.location,
            category=category if category is not None else (incident.category or "GENERAL"),
            priority=priority if priority is not None else (incident.priority or "P3"),
            assigned_team=(
                assigned_team
                if assigned_team is not None
                else (incident.assigned_team or "FACILITIES_DESK")
            ),
            requires_human_review=(
                requires_human_review
                if requires_human_review is not None
                else incident.requires_human_review
            ),
            reason=reason,
        )
