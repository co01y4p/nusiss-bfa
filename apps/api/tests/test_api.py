from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.core.database import Base, get_db
from app.core.models import UserModel
from app.main import app
from app.security.authentication import hash_password


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
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
        max_agent_steps=16,
        max_model_calls=10,
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def test_public_incident_flow_and_manager_authorization(client: TestClient) -> None:
    created_response = client.post(
        "/api/v1/incidents",
        json={"description": "Broken lobby light", "location": "Main lobby"},
    )
    assert created_response.status_code == 201
    created = created_response.json()

    tracked = client.get(f"/api/v1/incidents/track/{created['reference_code']}")
    assert tracked.status_code == 200
    assert tracked.json()["status"] == "RECEIVED"

    assert client.get("/api/v1/incidents").status_code == 401
    token_response = client.post(
        "/api/v1/auth/token",
        json={
            "email": "manager@example.com",
            "password": "correct-horse-battery-staple",
        },
    )
    assert token_response.status_code == 200
    headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}

    listed = client.get("/api/v1/incidents", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["incidents"][0]["reference_code"] == created["reference_code"]

    updated = client.patch(
        f"/api/v1/incidents/{created['id']}/status",
        headers=headers,
        json={"status": "IN_PROGRESS", "reason": "Technician dispatched to inspect lobby"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "IN_PROGRESS"
    assert updated.json()["override_reason"] == "Technician dispatched to inspect lobby"


def test_invalid_manager_credentials_are_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/token",
        json={"email": "manager@example.com", "password": "incorrect-password"},
    )

    assert response.status_code == 401


def test_building_layout_is_public_to_read_and_manager_only_to_write(
    client: TestClient,
) -> None:
    empty = client.get("/api/v1/facilities/layout")
    assert empty.status_code == 200
    assert empty.json()["floors"] == []

    layout = {
        "floors": [
            {
                "name": "Level 1",
                "facilities": [
                    {"name": "Toilet 1", "category": "PLUMBING"},
                    {"name": "Lift Lobby", "category": "LIFT"},
                ],
            },
        ],
    }
    assert client.put("/api/v1/facilities/layout", json=layout).status_code == 401

    token_response = client.post(
        "/api/v1/auth/token",
        json={
            "email": "manager@example.com",
            "password": "correct-horse-battery-staple",
        },
    )
    headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}

    saved = client.put("/api/v1/facilities/layout", headers=headers, json=layout)
    assert saved.status_code == 200
    saved_floors = saved.json()["floors"]
    assert saved_floors[0]["name"] == "Level 1"
    assert [f["name"] for f in saved_floors[0]["facilities"]] == ["Toilet 1", "Lift Lobby"]

    refetched = client.get("/api/v1/facilities/layout")
    assert refetched.status_code == 200
    assert refetched.json() == saved.json()


def test_assistant_persists_triage_and_protects_trace(client: TestClient) -> None:
    assistant_response = client.post(
        "/api/v1/assistant/messages",
        json={
            "message": "There is a gas smell near the lift lobby.",
            "location": "Block B level 2",
        },
    )
    assert assistant_response.status_code == 200
    assistant_result = assistant_response.json()
    assert assistant_result["outcome"] == "FINALIZED"
    assert "trace" not in assistant_result

    token_response = client.post(
        "/api/v1/auth/token",
        json={
            "email": "manager@example.com",
            "password": "correct-horse-battery-staple",
        },
    )
    headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}
    incidents = client.get("/api/v1/incidents", headers=headers).json()["incidents"]
    incident = next(
        item for item in incidents if item["reference_code"] == assistant_result["reference_code"]
    )
    assert incident["priority"] == "P1"

    assert client.get(f"/api/v1/incidents/{incident['id']}/trace").status_code == 401
    trace_response = client.get(
        f"/api/v1/incidents/{incident['id']}/trace",
        headers=headers,
    )
    assert trace_response.status_code == 200
    nodes = [step["node"] for step in trace_response.json()["trace"]]
    assert nodes[:4] == ["security", "intent", "create_incident", "intent_finalize"]
    assert "notify_critical" in nodes
    assert nodes[-1] == "finalize"


def test_assistant_returns_trace_when_requested(client: TestClient) -> None:
    assistant_response = client.post(
        "/api/v1/assistant/messages",
        json={
            "message": "What are the building hours?",
            "include_trace": True,
        },
    )
    assert assistant_response.status_code == 200
    assistant_result = assistant_response.json()
    assert assistant_result["outcome"] == "FINALIZED"
    assert "trace" in assistant_result
    assert len(assistant_result["trace"]) > 0
    nodes = [step["node"] for step in assistant_result["trace"]]
    assert "security" in nodes
    assert "intent" in nodes


def test_knowledge_document_chunk_preview(client: TestClient) -> None:
    created = client.post(
        "/api/v1/knowledge/documents",
        json={
            "title": "Parking Policy",
            "content": (
                "# Parking Policy\n\n"
                "## Visitor Parking\nVisitor parking is on B2.\n\n"
                "## EV Charging\nEV bays are on B2 Lots 10-20."
            ),
        },
    )
    assert created.status_code == 200
    doc = created.json()
    assert doc["chunk_count"] > 0

    preview = client.get(f"/api/v1/knowledge/documents/{doc['id']}/chunks")
    assert preview.status_code == 200
    chunks = preview.json()
    assert len(chunks) == doc["chunk_count"]
    assert chunks == sorted(chunks, key=lambda c: c["chunk_index"])
    assert any("Visitor Parking" in c["heading"] for c in chunks)

    missing = client.get("/api/v1/knowledge/documents/does-not-exist/chunks")
    assert missing.status_code == 404


def test_assistant_accepts_conversation_history(client: TestClient) -> None:
    first = client.post(
        "/api/v1/assistant/messages",
        json={"message": "Can someone take a look?", "include_trace": True},
    )
    assert first.status_code == 200
    assert first.json()["outcome"] == "NEEDS_CLARIFICATION"
    assert first.json()["message"].endswith("?")
    assert "clarification" in [step["node"] for step in first.json()["trace"]]

    second = client.post(
        "/api/v1/assistant/messages",
        json={
            "message": "The tap is leaking in the level 3 pantry.",
            "history": [
                {"role": "user", "content": "Can someone take a look?"},
                {"role": "assistant", "content": first.json()["message"]},
            ],
        },
    )
    assert second.status_code == 200
    assert second.json()["outcome"] == "FINALIZED"
    assert second.json()["reference_code"]


def test_assistant_rejects_oversized_history(client: TestClient) -> None:
    too_many_turns = client.post(
        "/api/v1/assistant/messages",
        json={
            "message": "Hello",
            "history": [{"role": "user", "content": f"turn {i}"} for i in range(7)],
        },
    )
    assert too_many_turns.status_code == 422

    too_long_turn = client.post(
        "/api/v1/assistant/messages",
        json={"message": "Hello", "history": [{"role": "user", "content": "x" * 2001}]},
    )
    assert too_long_turn.status_code == 422

    bad_role = client.post(
        "/api/v1/assistant/messages",
        json={"message": "Hello", "history": [{"role": "system", "content": "hi"}]},
    )
    assert bad_role.status_code == 422
