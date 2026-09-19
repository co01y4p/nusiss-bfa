import pytest

from app.domain.incidents.models import IncidentCreate
from app.services.incident_service import IncidentService, InvalidStatusTransitionError
from tests.fakes import InMemoryIncidentRepository


def test_incident_is_created_without_llm() -> None:
    repository = InMemoryIncidentRepository()
    service = IncidentService(repository)

    incident = service.create(IncidentCreate(description="Broken light", location="Lobby"))

    assert incident.status.value == "RECEIVED"
    assert incident.reference_code.startswith("BFA-")


def test_invalid_status_jump_is_rejected() -> None:
    repository = InMemoryIncidentRepository()
    service = IncidentService(repository)
    incident = service.create(IncidentCreate(description="Broken light", location="Lobby"))

    with pytest.raises(InvalidStatusTransitionError):
        service.update_status(incident.id, "CLOSED", reason="Direct close attempt")


def test_valid_status_transition_stores_reason() -> None:
    repository = InMemoryIncidentRepository()
    service = IncidentService(repository)
    incident = service.create(IncidentCreate(description="Broken light", location="Lobby"))

    updated = service.update_status(
        incident.id, "IN_PROGRESS", reason="Operations crew on site"
    )

    assert updated is not None
    assert updated.status.value == "IN_PROGRESS"
    assert updated.override_reason == "Operations crew on site"
