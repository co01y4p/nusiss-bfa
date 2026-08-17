import uuid
from datetime import UTC, datetime

from app.domain.incidents.models import Incident, IncidentStatus


class InMemoryIncidentRepository:
    def __init__(self) -> None:
        self.items: dict[str, Incident] = {}

    def create(self, *, description: str, location: str) -> Incident:
        incident_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        incident = Incident(
            id=incident_id,
            reference_code=f"BFA-{len(self.items) + 1:010d}",
            description=description,
            location=location,
            status=IncidentStatus.RECEIVED,
            created_at=now,
            updated_at=now,
        )
        self.items[incident_id] = incident
        return incident

    def get_by_id(self, incident_id: str) -> Incident | None:
        return self.items.get(incident_id)

    def get_by_reference(self, reference_code: str) -> Incident | None:
        return next(
            (item for item in self.items.values() if item.reference_code == reference_code.upper()),
            None,
        )

    def list_recent(self, *, limit: int = 200, offset: int = 0) -> list[Incident]:
        return list(self.items.values())[offset : offset + limit]

    def update_status(self, incident_id: str, status: str) -> Incident | None:
        incident = self.items.get(incident_id)
        if incident is None:
            return None
        updated = incident.model_copy(
            update={"status": IncidentStatus(status), "updated_at": datetime.now(UTC)}
        )
        self.items[incident_id] = updated
        return updated

    def update_triage(
        self,
        incident_id: str,
        *,
        location: str,
        category: str,
        priority: str,
        assigned_team: str,
        requires_human_review: bool,
    ) -> Incident | None:
        incident = self.items.get(incident_id)
        if incident is None:
            return None
        updated = incident.model_copy(
            update={
                "location": location,
                "category": category,
                "priority": priority,
                "assigned_team": assigned_team,
                "requires_human_review": requires_human_review,
                "updated_at": datetime.now(UTC),
            }
        )
        self.items[incident_id] = updated
        return updated


class InMemoryWorkflowRunRepository:
    def __init__(self) -> None:
        self.runs: list[dict[str, object]] = []

    def save(
        self,
        *,
        incident_id: str | None,
        input_text: str,
        outcome: str,
        final_response: str,
        trace: list[dict[str, object]],
    ) -> str:
        run_id = str(uuid.uuid4())
        self.runs.append(
            {
                "id": run_id,
                "incident_id": incident_id,
                "input_text": input_text,
                "outcome": outcome,
                "final_response": final_response,
                "trace": trace,
                "created_at": datetime.now(UTC),
            }
        )
        return run_id

    def get_for_incident(self, incident_id: str) -> dict[str, object] | None:
        return next(
            (run for run in reversed(self.runs) if run["incident_id"] == incident_id),
            None,
        )
