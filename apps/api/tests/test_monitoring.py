import json
import logging
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.agents.base import BaseAgent, StrictAgentModel
from app.agents.intent import Intent, IntentAgent
from app.main import app
from app.monitoring.logging import (
    StructuredJsonFormatter,
)
from app.monitoring.metrics import (
    AGENT_RETRIES_TOTAL,
    AGENT_RUNS_TOTAL,
    HTTP_REQUESTS_TOTAL,
    LLM_SCHEMA_VALIDATION_FAILURES_TOTAL,
    TOOL_INVOCATIONS_TOTAL,
    WORKFLOW_RUNS_TOTAL,
    record_agent_run,
    record_workflow_run,
)
from app.tools.registry import ToolRegistry
from tests.test_workflow import make_workflow


def test_metrics_endpoint_returns_prometheus_exposition() -> None:
    # Trigger an agent run and workflow metric to ensure data is present
    record_agent_run("test_agent", "success", 0.123)
    record_workflow_run("FINALIZED")

    with TestClient(app) as client:
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        text = response.text
        assert "agent_runs_total" in text
        assert "agent_duration_seconds" in text
        assert "agent_retries_total" in text
        assert "llm_tokens_total" in text
        assert "llm_schema_validation_failures_total" in text
        assert "tool_invocations_total" in text
        assert "workflow_runs_total" in text
        assert "http_requests_total" in text


def test_http_request_metrics_recorded_by_middleware() -> None:
    with TestClient(app) as client:
        initial_val = HTTP_REQUESTS_TOTAL.labels(
            method="GET", path="/", status_code="200"
        )._value.get()
        res = client.get("/")
        assert res.status_code == 200
        after_val = HTTP_REQUESTS_TOTAL.labels(
            method="GET", path="/", status_code="200"
        )._value.get()
        assert after_val == initial_val + 1


class DummyAgentOutput(StrictAgentModel):
    message: str


class DummyAgent(BaseAgent[DummyAgentOutput]):
    name = "dummy_agent"
    output_schema = DummyAgentOutput

    def fallback(self, payload: dict, error: Exception) -> DummyAgentOutput:
        return DummyAgentOutput(message="fallback")


@pytest.mark.asyncio
async def test_agent_metrics_recorded_on_success() -> None:
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = DummyAgentOutput(message="hello")

    agent = DummyAgent(mock_llm, model="test-model", timeout_seconds=5, system_prompt="Test prompt")
    before_runs = AGENT_RUNS_TOTAL.labels(agent="dummy_agent", status="success")._value.get()

    output = await agent.run({"text": "hi"})
    assert output.message == "hello"

    after_runs = AGENT_RUNS_TOTAL.labels(agent="dummy_agent", status="success")._value.get()
    assert after_runs == before_runs + 1


@pytest.mark.asyncio
async def test_agent_metrics_and_schema_failure_recorded_on_fallback() -> None:
    from pydantic import ValidationError

    mock_llm = AsyncMock()
    # Simulate a validation failure when parsing LLM output
    try:
        DummyAgentOutput.model_validate({"extra_field": "invalid"})
    except ValidationError as val_err:
        mock_llm.generate.side_effect = val_err

    agent = DummyAgent(mock_llm, model="test-model", timeout_seconds=5, system_prompt="Test prompt")
    before_fallbacks = AGENT_RUNS_TOTAL.labels(agent="dummy_agent", status="fallback")._value.get()
    before_failures = LLM_SCHEMA_VALIDATION_FAILURES_TOTAL.labels(agent="dummy_agent")._value.get()

    output = await agent.run({"text": "hi"})
    assert output.message == "fallback"

    after_fallbacks = AGENT_RUNS_TOTAL.labels(agent="dummy_agent", status="fallback")._value.get()
    after_failures = LLM_SCHEMA_VALIDATION_FAILURES_TOTAL.labels(agent="dummy_agent")._value.get()

    assert after_fallbacks == before_fallbacks + 1
    assert after_failures == before_failures + 1


@pytest.mark.asyncio
async def test_intent_agent_records_retry_on_missing_tool_call() -> None:
    from app.agents.intent import IntentOutput
    from app.llm.gateway import ToolCallingResult

    mock_llm = AsyncMock()
    registry = ToolRegistry()

    class CreateIncidentArgs(BaseModel):
        description: str

    def handle_create(args: CreateIncidentArgs) -> dict:
        return {"id": "inc-123", "reference_code": "BFA-ABC123"}

    registry.register(
        name="create_incident",
        description="Creates incident",
        input_schema=CreateIncidentArgs,
        required_role="SYSTEM",
        handler=handle_create,
    )

    # First call misses tool, second call also misses tool, then third succeeds
    mock_llm.generate_with_tools.side_effect = [
        ToolCallingResult(
            output=IntentOutput(
                intent=Intent.INCIDENT_REPORT,
                incident_id=None,
                reference_code=None,
                confidence=0.9,
                reason_codes=["DEFECT"],
            ),
            tool_calls=[],
            model_calls=1,
            first_model_input={},
        ),
        ToolCallingResult(
            output=IntentOutput(
                intent=Intent.INCIDENT_REPORT,
                incident_id=None,
                reference_code=None,
                confidence=0.9,
                reason_codes=["DEFECT"],
            ),
            tool_calls=[],
            model_calls=1,
            first_model_input={},
        ),
        ToolCallingResult(
            output=IntentOutput(
                intent=Intent.OTHER,
                incident_id=None,
                reference_code=None,
                confidence=0.8,
                reason_codes=["OTHER"],
            ),
            tool_calls=[],
            model_calls=1,
            first_model_input={},
        ),
    ]

    agent = IntentAgent(mock_llm, model="test-model", timeout_seconds=5, tools=registry)
    before_retries = AGENT_RETRIES_TOTAL.labels(
        agent="intent", reason="MISSING_TOOL_CALL"
    )._value.get()

    await agent.run({"text": "Leaking pipe"})

    after_retries = AGENT_RETRIES_TOTAL.labels(
        agent="intent", reason="MISSING_TOOL_CALL"
    )._value.get()
    assert after_retries >= before_retries + 2


@pytest.mark.asyncio
async def test_tool_invocation_metrics_recorded() -> None:
    registry = ToolRegistry()

    class ArgSchema(BaseModel):
        value: int

    registry.register(
        name="test_tool",
        description="A test tool",
        input_schema=ArgSchema,
        required_role="PUBLIC",
        handler=lambda args: args.value * 2,
    )

    before_success = TOOL_INVOCATIONS_TOTAL.labels(tool="test_tool", status="success")._value.get()
    before_error = TOOL_INVOCATIONS_TOTAL.labels(tool="test_tool", status="error")._value.get()

    res_ok = await registry.execute("test_tool", {"value": 5})
    assert res_ok.success is True

    res_err = await registry.execute("test_tool", {"value": "not_an_int"})
    assert res_err.success is False

    after_success = TOOL_INVOCATIONS_TOTAL.labels(tool="test_tool", status="success")._value.get()
    after_error = TOOL_INVOCATIONS_TOTAL.labels(tool="test_tool", status="error")._value.get()

    assert after_success == before_success + 1
    assert after_error == before_error + 1


@pytest.mark.asyncio
async def test_workflow_runs_total_incremented() -> None:
    workflow, _, _ = make_workflow()

    before_finalized = WORKFLOW_RUNS_TOTAL.labels(outcome="FINALIZED")._value.get()
    state = await workflow.run(text="The elevator is stuck on floor 3", location="Block A")

    assert state.outcome == "FINALIZED"
    after_finalized = WORKFLOW_RUNS_TOTAL.labels(outcome="FINALIZED")._value.get()
    assert after_finalized == before_finalized + 1


def test_structured_json_logging_and_redaction() -> None:
    formatter = StructuredJsonFormatter()
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="User authenticated with Bearer eyJhbGciOiJIUzI1Ni.secret and api_key=topsecret123",
        args=(),
        exc_info=None,
    )
    # Add structured extra attributes
    record.reason_codes = ["TEST_CODE"]
    record.jwt_secret = "super-secret-jwt"
    record.chain_of_thought = "Thinking about user intent..."

    formatted = formatter.format(record)
    log_data = json.loads(formatted)

    assert log_data["level"] == "INFO"
    assert log_data["logger"] == "app.test"
    # Ensure secrets and bearer tokens are redacted
    assert "Bearer [REDACTED]" in log_data["message"]
    assert "secret=[REDACTED]" in log_data["message"]
    assert "topsecret123" not in log_data["message"]

    # Ensure allowed fields are present
    assert log_data["reason_codes"] == ["TEST_CODE"]

    # Ensure forbidden fields (jwt_secret, chain_of_thought) are stripped
    assert "jwt_secret" not in log_data
    assert "chain_of_thought" not in log_data
