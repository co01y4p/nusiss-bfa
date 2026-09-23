import pytest

from app.domain.incidents.models import IncidentCreate
from app.rag.embeddings import FakeEmbeddings
from app.services.incident_service import IncidentService, InvalidStatusTransitionError
from tests.fakes import InMemoryIncidentRepository


@pytest.mark.asyncio
async def test_incident_is_created_without_llm() -> None:
    repository = InMemoryIncidentRepository()
    service = IncidentService(repository)

    incident = await service.create(IncidentCreate(description="Broken light", location="Lobby"))

    assert incident.status.value == "RECEIVED"
    assert incident.reference_code.startswith("BFA-")


@pytest.mark.asyncio
async def test_invalid_status_jump_is_rejected() -> None:
    repository = InMemoryIncidentRepository()
    service = IncidentService(repository)
    incident = await service.create(IncidentCreate(description="Broken light", location="Lobby"))

    with pytest.raises(InvalidStatusTransitionError):
        service.update_status(incident.id, "CLOSED", reason="Direct close attempt")


@pytest.mark.asyncio
async def test_valid_status_transition_stores_reason() -> None:
    repository = InMemoryIncidentRepository()
    service = IncidentService(repository)
    incident = await service.create(IncidentCreate(description="Broken light", location="Lobby"))

    updated = service.update_status(incident.id, "IN_PROGRESS", reason="Operations crew on site")

    assert updated is not None
    assert updated.status.value == "IN_PROGRESS"
    assert updated.override_reason == "Operations crew on site"


class FailingEmbeddings:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding provider unavailable")

    async def embed_query(self, text: str) -> list[float]:
        raise RuntimeError("embedding provider unavailable")


@pytest.mark.asyncio
async def test_incident_is_still_created_when_embedding_fails() -> None:
    repository = InMemoryIncidentRepository()
    service = IncidentService(repository, FailingEmbeddings())

    incident = await service.create(IncidentCreate(description="Broken light", location="Lobby"))

    assert incident.reference_code.startswith("BFA-")
    assert repository.get_by_id(incident.id) is not None
    assert incident.id not in repository._embeddings


@pytest.mark.asyncio
async def test_unspecified_location_is_not_embedded() -> None:
    repository = InMemoryIncidentRepository()
    service = IncidentService(repository, FakeEmbeddings(dim=1536))

    unspecified = await service.create(
        IncidentCreate(description="Broken light", location="Unspecified")
    )
    specified = await service.create(IncidentCreate(description="Broken light", location="Lobby"))

    assert unspecified.id not in repository._embeddings
    assert specified.id in repository._embeddings
