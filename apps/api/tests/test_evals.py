import json
from collections.abc import Generator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import app.api.v1.routers.evals as evals_router
from app.core.config import Settings, get_settings
from app.llm.factory import build_structured_llm
from app.llm.providers.openai_compatible import OpenAICompatibleStructuredLLM
from app.main import app

DATASET_DIR = Path(__file__).parents[3] / "evals" / "promptfoo" / "datasets"


def load_cases(name: str) -> list[dict[str, object]]:
    lines = (DATASET_DIR / name).read_text(encoding="utf-8").splitlines()
    return [json.loads(line)["vars"] for line in lines if line]


@pytest.fixture
def fake_provider_client() -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_settings] = lambda: Settings(
        app_env="test",
        llm_provider="fake",
        evaluation_enabled=True,
        evaluation_key="test-evaluation-key",
    )
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_evaluation_endpoint_requires_key(fake_provider_client: TestClient) -> None:
    body = {"case_id": "auth-check", "suite": "intent", "message": "Hello"}
    assert fake_provider_client.post("/api/v1/evals/run", json=body).status_code == 401


def test_evaluation_endpoint_rejects_fake_provider(fake_provider_client: TestClient) -> None:
    response = fake_provider_client.post(
        "/api/v1/evals/run",
        json={"case_id": "fake-check", "suite": "intent", "message": "Hello"},
        headers={"X-Evaluation-Key": "test-evaluation-key"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "A real evaluation LLM is not configured"


def test_llm_factory_rejects_fake_for_evaluation() -> None:
    with pytest.raises(RuntimeError, match="real LLM provider"):
        build_structured_llm(Settings(llm_provider="fake"), allow_fake=False)


def test_evaluation_endpoint_uses_real_provider_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "gpt-5-nano"
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "intent": "OTHER",
                                        "incident_id": None,
                                        "reference_code": None,
                                        "confidence": 0.95,
                                        "reason_codes": ["GREETING"],
                                    }
                                ),
                            }
                        ],
                    }
                ],
            },
        )

    provider = OpenAICompatibleStructuredLLM(
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        api_style="responses",
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(evals_router, "build_structured_llm", lambda settings, allow_fake: provider)
    app.dependency_overrides[get_settings] = lambda: Settings(
        app_env="test",
        llm_provider="openai",
        llm_api_key="test-key",
        evaluation_enabled=True,
        evaluation_key="test-evaluation-key",
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/evals/run",
                json={"case_id": "real-check", "suite": "intent", "message": "Hello"},
                headers={"X-Evaluation-Key": "test-evaluation-key"},
            )
        assert response.status_code == 200
        result = response.json()
        assert result["provider"] == "openai"
        assert result["classifier_model"] == "gpt-5-nano"
        assert result["model_invoked"] is True
        assert result["intent"] == "OTHER"
    finally:
        app.dependency_overrides.clear()


def test_evaluation_endpoint_reports_failed_real_model_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(503, json={"error": {"message": "Unavailable"}})

    provider = OpenAICompatibleStructuredLLM(
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        api_style="responses",
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(evals_router, "build_structured_llm", lambda settings, allow_fake: provider)
    app.dependency_overrides[get_settings] = lambda: Settings(
        app_env="test",
        llm_provider="openai",
        llm_api_key="test-key",
        evaluation_enabled=True,
        evaluation_key="test-evaluation-key",
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/evals/run",
                json={"case_id": "failed-call", "suite": "intent", "message": "Hello"},
                headers={"X-Evaluation-Key": "test-evaluation-key"},
            )
        assert response.status_code == 502
        assert "real LLM call did not complete" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_evaluation_endpoint_is_hidden_in_production() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        app_env="production",
        llm_provider="openai",
        llm_api_key="test-key",
        evaluation_enabled=True,
        evaluation_key="test-evaluation-key",
        jwt_secret="a-secure-production-secret-with-more-than-32-characters",
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/evals/run",
                json={"case_id": "prod-check", "suite": "intent", "message": "Hello"},
                headers={"X-Evaluation-Key": "test-evaluation-key"},
            )
            assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_reviewed_dataset_shape_and_coverage() -> None:
    intent_cases = load_cases("intent.jsonl")
    incident_cases = load_cases("incidents.jsonl")
    safety_cases = load_cases("safety_critical.jsonl")
    qa_cases = load_cases("facility_qa.jsonl")
    injection_cases = load_cases("prompt_injection.jsonl")
    all_cases = intent_cases + incident_cases + safety_cases + qa_cases + injection_cases

    assert len(all_cases) == 92
    assert len({str(case["case_id"]) for case in all_cases}) == 92
    assert len(intent_cases) == 20
    assert len(incident_cases) == 30
    assert len(safety_cases) == 12
    assert len(qa_cases) == 20
    assert len(injection_cases) == 10
    assert {str(case["expected_category"]) for case in incident_cases} == {
        "HVAC",
        "ELECTRICAL",
        "PLUMBING",
        "LIFT",
        "ACCESS",
        "GENERAL",
    }
    assert all(case["expected_priority"] == "P1" for case in safety_cases)
    assert all(case["expected_injection"] is True for case in injection_cases)
