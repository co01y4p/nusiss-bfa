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
        json={"status": "IN_PROGRESS"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "IN_PROGRESS"


def test_invalid_manager_credentials_are_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/token",
        json={"email": "manager@example.com", "password": "incorrect-password"},
    )

    assert response.status_code == 401


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
    assert nodes[:3] == ["security", "intent", "persist_incident"]
    assert "notify_critical" in nodes
    assert nodes[-1] == "finalize"
