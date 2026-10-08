"""Failure-injection tests: every external dependency can fail without crashing the API.

Each test breaks one dependency (LLM provider, model output, retriever, database, ...) and
asserts what the occupant and the manager see. The table in docs/plan/gap-closure/g6 lists
the same scenarios.
"""

from collections.abc import Generator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.llm.circuit_breaker import CircuitBreaker
from app.llm.providers import openai_compatible
from app.llm.providers.openai_compatible import OpenAICompatibleStructuredLLM
from app.rag.retriever import KnowledgeRetriever
from tests.test_api import client  # noqa: F401  (pytest fixture)
from tests.test_workflow import make_workflow

HAZARD = "There is a strong gas smell in the pantry."
ROUTINE = "The power socket in room 105 is not working."


@pytest.fixture(autouse=True)
def instant_retries(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Skip the backoff sleeps so provider failures cost no wall-clock time."""
    original = openai_compatible.with_transient_retries

    async def no_delay(operation: Any, *, retries: int = 2, base_delay_seconds: float = 0.1) -> Any:
        return await original(operation, retries=retries, base_delay_seconds=0)

    monkeypatch.setattr(openai_compatible, "with_transient_retries", no_delay)
    yield


def provider(handler: Any, *, breaker: CircuitBreaker | None = None) -> Any:
    return OpenAICompatibleStructuredLLM(
        base_url="https://llm.test/v1",
        api_key="test-key",
        api_style="responses",
        transport=httpx.MockTransport(handler),
        circuit_breaker=breaker or CircuitBreaker(failure_threshold=1000, name="failure-test"),
    )


def unavailable(request: httpx.Request) -> httpx.Response:
    return httpx.Response(503, json={"error": {"message": "service unavailable"}})


class FailingRetriever:
    async def search(self, *args: object, **kwargs: object) -> list[object]:
        raise RuntimeError("embeddings API unreachable")


@pytest.mark.asyncio
async def test_retrieval_failure_hands_off_to_a_manager_instead_of_raising() -> None:
    workflow, _, runs = make_workflow()
    workflow.retriever = FailingRetriever()  # type: ignore[assignment]

    state = await workflow.run(text="What are the general building hours?")

    assert state.outcome == "HUMAN_REVIEW"
    assert (
        state.final_response == "The automated workflow stopped safely. A manager will review it."
    )
    step = next(s for s in state.trace if s.node == "human_review")
    assert step.reason_codes == ["WORKFLOW_ERROR"]
    assert step.output == {"error": "RuntimeError"}
    assert runs.runs[0]["outcome"] == "HUMAN_REVIEW"  # still recorded for the audit trail


def test_assistant_endpoint_returns_200_not_500_when_retrieval_fails(
    client: TestClient,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(self: KnowledgeRetriever, *args: object, **kwargs: object) -> list[object]:
        raise RuntimeError("embeddings API unreachable")

    monkeypatch.setattr(KnowledgeRetriever, "search", boom)

    response = client.post(
        "/api/v1/assistant/messages", json={"message": "What are the building hours?"}
    )

    assert response.status_code == 200
    assert response.json()["outcome"] == "HUMAN_REVIEW"


@pytest.mark.asyncio
async def test_unexpected_error_after_an_incident_exists_keeps_and_flags_the_incident() -> None:
    workflow, incidents, _ = make_workflow()

    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("downstream failure")

    workflow.review.run = boom  # type: ignore[method-assign]

    state = await workflow.run(text="The lift button is broken.", location="Level 2")

    assert state.outcome == "HUMAN_REVIEW"
    assert state.incident_id is not None
    stored = incidents.get_by_id(state.incident_id)
    assert stored is not None
    assert stored.requires_human_review is True
