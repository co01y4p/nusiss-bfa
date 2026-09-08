from datetime import datetime
from typing import Protocol

from app.domain.incidents.models import Incident


class IncidentRepository(Protocol):
    def create(self, *, description: str, location: str) -> Incident: ...

    def get_by_id(self, incident_id: str) -> Incident | None: ...

    def get_by_reference(self, reference_code: str) -> Incident | None: ...

    def list_recent(self, *, limit: int = 200, offset: int = 0) -> list[Incident]: ...

    def find_similar(
        self,
        *,
        location: str,
        since: datetime,
        exclude_id: str | None = None,
        limit: int = 5,
    ) -> list[Incident]: ...

    def update_status(self, incident_id: str, status: str) -> Incident | None: ...

    def update_triage(
        self,
        incident_id: str,
        *,
        location: str,
        category: str,
        priority: str,
        assigned_team: str,
        requires_human_review: bool,
    ) -> Incident | None: ...


class WorkflowRunRepository(Protocol):
    def save(
        self,
        *,
        incident_id: str | None,
        input_text: str,
        outcome: str,
        final_response: str,
        trace: list[dict[str, object]],
    ) -> str: ...

    def get_for_incident(self, incident_id: str) -> dict[str, object] | None: ...
