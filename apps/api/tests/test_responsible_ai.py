import copy
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.agents.assignment import AssignmentAgent
from app.agents.classification import ClassificationAgent
from app.agents.extraction import ExtractionAgent
from app.agents.intent import IntentAgent
from app.agents.priority import PriorityAgent
from app.agents.response import ResponseAgent
from app.agents.review import ReviewAgent
from app.agents.security import SecurityAgent
from app.core.config import Settings, get_settings
from app.core.database import Base, get_db
from app.core.models import UserModel
from app.domain.incidents.policies import determine_priority
from app.llm.fake import FakeStructuredLLM
from app.main import app
from app.rag.citation_validator import CitationValidator
from app.rag.embeddings import FakeEmbeddings
from app.rag.retriever import KnowledgeRetriever
from app.repositories.postgres.knowledge import SqlAlchemyKnowledgeRepository
from app.security.authentication import hash_password
from app.tools.incident_tools import register_incident_tools
from app.tools.registry import ToolRegistry
from app.workflows.facility_graph import FacilityWorkflow
from tests.fakes import InMemoryIncidentRepository, InMemoryWorkflowRunRepository


def make_test_workflow(
    llm: FakeStructuredLLM | None = None,
    knowledge_session: Session | None = None,
) -> tuple[FacilityWorkflow, InMemoryIncidentRepository, InMemoryWorkflowRunRepository]:
    provider = llm or FakeStructuredLLM()
    settings = Settings(
        llm_provider="fake",
        max_agent_steps=16,
        max_model_calls=10,
        agent_timeout_seconds=1,
        workflow_timeout_seconds=5,
    )
    args = {"llm": provider, "model": "fake", "timeout_seconds": 1}
    incidents = InMemoryIncidentRepository()
    runs = InMemoryWorkflowRunRepository()
    tools = ToolRegistry()
    register_incident_tools(tools, incidents)

    retriever = None
    if knowledge_session is not None:
        k_repo = SqlAlchemyKnowledgeRepository(knowledge_session)
        embeddings = FakeEmbeddings(dim=1536)
        retriever = KnowledgeRetriever(
            repository=k_repo, embeddings=embeddings, default_similarity_threshold=0.70
        )

    workflow = FacilityWorkflow(
        settings=settings,
        incident_repository=incidents,
        workflow_repository=runs,
        security=SecurityAgent(**args),
        intent=IntentAgent(**args, tools=tools),
        extraction=ExtractionAgent(**args),
        classification=ClassificationAgent(**args),
        priority=PriorityAgent(**args),
        assignment=AssignmentAgent(**args),
        response=ResponseAgent(**args),
        review=ReviewAgent(**args),
        tools=tools,
        retriever=retriever,
        citation_validator=CitationValidator(),
    )
    return workflow, incidents, runs


@pytest.fixture
def rai_client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    with session_factory() as session:
        session.add(
            UserModel(
                email="manager@example.com",
                password_hash=hash_password("correct-horse-battery-staple"),
                role="MANAGER",
            )
        )
        session.commit()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: Settings(
        app_env="test",
        llm_provider="fake",
        classifier_model="fake-classifier",
        generator_model="fake-generator",
        jwt_secret="test-secret-test-secret-test-secret-1234",
    )
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_critical_hazard_forces_p1_and_human_review() -> None:
    """HOR-01: Critical hazard keywords (e.g. 'gas smell', 'smoke') must force P1 priority

    and lock requires_human_review to True, regardless of model output.
    """
    workflow, incidents, _ = make_test_workflow()

    state = await workflow.run(
        text=(
            "Emergency! There is a strong gas smell and smoke coming from the 3rd floor cafeteria."
        ),
        location="Cafeteria Level 3",
    )

    assert state.outcome == "FINALIZED"
    assert len(incidents.items) == 1
    created_incident = next(iter(incidents.items.values()))
    assert created_incident.priority == "P1"
    assert created_incident.requires_human_review is True


def test_low_confidence_classification_flags_human_review() -> None:
    """HOR-02: Ambiguous or low-confidence triage decisions must automatically
    route to manual review with requires_human_review = True.
    """
    priority, reasons, requires_review = determine_priority(
        set(),
        "P2",
        0.45,  # Below operational confidence threshold
        text="Some strange noise from ceiling",
    )

    assert priority == "P3"  # Degraded to safe standard triage
    assert "LOW_CONFIDENCE_MANUAL_REVIEW" in reasons
    assert requires_review is True


@pytest.mark.asyncio
async def test_rag_missing_knowledge_returns_safe_fallback() -> None:
    """HOR-03: Facility Q&A with no matching knowledge chunks must return the safe
    fallback message instead of hallucinating building rules.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    try:
        workflow, incidents, _ = make_test_workflow(knowledge_session=session)

        # Empty knowledge base queried about an unverified topic
        state = await workflow.run(
            text="What is the official building policy on bringing pet alpacas into lecture halls?"
        )

        assert state.outcome == "FINALIZED"
        assert state.final_response == (
            "I do not have enough approved facility information to answer that question."
        )
        # Ensure no accidental incident was logged
        assert len(incidents.items) == 0
    finally:
        session.close()


@pytest.mark.asyncio
async def test_trace_immutability_after_status_override() -> None:
    """HOR-05 & Trace Immutability: When a manager overrides an incident status
    with a mandatory reason, the original workflow trace remains unmodified.
    """
    workflow, incidents, runs = make_test_workflow()

    state = await workflow.run(
        text="Water pipe leaking in corridor near room 204.",
        location="Level 2 corridor",
    )

    assert state.outcome == "FINALIZED"
    assert len(runs.runs) == 1
    saved_run = runs.runs[0]
    saved_trace_snapshot = copy.deepcopy(saved_run["trace"])

    created_incident = next(iter(incidents.items.values()))
    assert created_incident.status.value == "RECEIVED"
    assert created_incident.override_reason is None

    # Manager executes status override
    updated = incidents.update_status(
        created_incident.id,
        "IN_PROGRESS",
        reason="Plumber dispatched on site with replacement valve",
    )

    assert updated is not None
    assert updated.status.value == "IN_PROGRESS"
    assert updated.override_reason == "Plumber dispatched on site with replacement valve"

    # Verify that the original workflow run trace was NOT mutated
    assert saved_run["trace"] == saved_trace_snapshot


def test_status_update_requires_reason_and_rejects_empty(rai_client: TestClient) -> None:
    """Status update endpoint must enforce 1-500 char reason.

    Rejects missing or empty reason with 422.
    """
    login_res = rai_client.post(
        "/api/v1/auth/token",
        json={"email": "manager@example.com", "password": "correct-horse-battery-staple"},
    )
    assert login_res.status_code == 200
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    create_res = rai_client.post(
        "/api/v1/incidents",
        json={"description": "Elevator door stuck open", "location": "Lift Lobby B"},
    )
    assert create_res.status_code == 201
    incident_id = create_res.json()["id"]

    # Missing reason field -> 422
    res_missing_reason = rai_client.patch(
        f"/api/v1/incidents/{incident_id}/status",
        headers=headers,
        json={"status": "IN_PROGRESS"},
    )
    assert res_missing_reason.status_code == 422

    # Empty reason string -> 422
    res_empty_reason = rai_client.patch(
        f"/api/v1/incidents/{incident_id}/status",
        headers=headers,
        json={"status": "IN_PROGRESS", "reason": ""},
    )
    assert res_empty_reason.status_code == 422

    # Valid reason -> 200 with persisted override_reason
    res_valid = rai_client.patch(
        f"/api/v1/incidents/{incident_id}/status",
        headers=headers,
        json={
            "status": "IN_PROGRESS",
            "reason": "Lift technician arrived on site; power isolated.",
        },
    )
    assert res_valid.status_code == 200
    assert res_valid.json()["status"] == "IN_PROGRESS"
    assert res_valid.json()["override_reason"] == "Lift technician arrived on site; power isolated."
