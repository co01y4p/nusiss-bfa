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

    def update_status(self, incident_id: str, target_status: str) -> Incident | None:
        incident = self.repository.get_by_id(incident_id)
        if incident is None:
            return None
        if not can_transition_status(incident.status.value, target_status):
            raise InvalidStatusTransitionError(
                f"Cannot transition from {incident.status.value} to {target_status}"
            )
        return self.repository.update_status(incident_id, target_status)
