import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.agents.intent import Intent
from app.core.config import Settings
from app.monitoring.langfuse import LangfuseTraceContext, LangfuseTracer
from app.workflows.facility_graph import FacilityWorkflow


def test_tracer_disabled_when_keys_missing() -> None:
    settings = Settings(
        langfuse_enabled=True,
        langfuse_public_key="",
        langfuse_secret_key="",
    )
    tracer = LangfuseTracer(settings=settings)
    assert not tracer.enabled

    ctx = tracer.start_trace(
        name="test-trace",
        input_data={"message": "hello"},
    )
    assert isinstance(ctx, LangfuseTraceContext)
    gen_id = ctx.log_generation(
        name="test-gen",
        model="gpt-5-nano",
        input_data={"prompt": "hi"},
        output_data={"text": "hello"},
    )
    assert gen_id.startswith("gen-")
    span_id = ctx.log_span(name="test-span", input_data={"a": 1})
    assert span_id.startswith("span-")
    ctx.end(output_data={"result": "ok"})


@pytest.mark.asyncio
async def test_tracer_flushes_events_with_proper_schema() -> None:
    recorded_requests: list[httpx.Request] = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        recorded_requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(mock_handler)

    tracer = LangfuseTracer(
        enabled=True,
        public_key="pk-lf-test",
        secret_key="sk-lf-test",
        host="https://mock.langfuse.com",
        transport=transport,
    )
    assert tracer.enabled

    ctx = tracer.start_trace(
        name="facility-assistant",
        trace_id="tr-test-123",
        input_data={"message": "My NRIC is S1234567A and phone is 91234567"},
        metadata={"token": "secret_bearer_token", "env": "test"},
    )

    ctx.log_generation(
        name="agent:intent",
        model="gpt-5-nano",
        input_data={"text": "My NRIC is S1234567A"},
        output_data={"intent": "GENERAL_QUERY"},
        prompt_tokens=50,
        completion_tokens=20,
    )

    ctx.log_span(
        name="step:retrieval",
        input_data={"query": "facility info"},
        output_data={"chunks": ["chunk1"]},
    )

    ctx.end(output_data={"response": "Here is your answer."})

    flushed = await ctx.flush()
    assert flushed is True
    assert len(recorded_requests) == 1

    req = recorded_requests[0]
    assert req.url == "https://mock.langfuse.com/api/public/ingestion"
    assert req.headers.get("authorization", "").startswith("Basic ")

    payload = json.loads(req.content.decode("utf-8"))
    assert "batch" in payload
    batch = payload["batch"]
    assert len(batch) >= 4  # trace-create, generation, span, trace update

    # Verify PII redaction on input
    trace_event = next(e for e in batch if e["type"] == "trace-create")
    assert "[NRIC/FIN REDACTED]" in str(trace_event["body"]["input"])
    assert "[PHONE REDACTED]" in str(trace_event["body"]["input"])
    # Verify secret token suppression (completely stripped from metadata)
    assert "token" not in trace_event["body"]["metadata"]
    assert trace_event["body"]["metadata"]["env"] == "test"

    # Verify generation event
    gen_event = next(e for e in batch if e["body"].get("type") == "GENERATION")
    assert gen_event["body"]["model"] == "gpt-5-nano"
    assert gen_event["body"]["usage"]["promptTokens"] == 50
    assert gen_event["body"]["usage"]["completionTokens"] == 20
    assert gen_event["body"]["usage"]["totalTokens"] == 70
    assert "[NRIC/FIN REDACTED]" in str(gen_event["body"]["input"])

    # Verify span event
    span_event = next(e for e in batch if e["body"].get("type") == "SPAN")
    assert span_event["body"]["name"] == "step:retrieval"


@pytest.mark.asyncio
async def test_tracer_network_failure_is_resilient() -> None:
    def failing_handler(request: httpx.Request) -> httpx.Response:
        del request
        raise httpx.ConnectError("Network unreachable")

    transport = httpx.MockTransport(failing_handler)

    tracer = LangfuseTracer(
        enabled=True,
        public_key="pk-lf-test",
        secret_key="sk-lf-test",
        transport=transport,
    )

    ctx = tracer.start_trace(name="test")
    ctx.log_span(name="step:1")
    ctx.end()

    # Should not raise exception, but return False gracefully
    success = await ctx.flush()
    assert success is False


@pytest.mark.asyncio
async def test_workflow_integrates_with_langfuse_tracer() -> None:
    mock_tracer = MagicMock(spec=LangfuseTracer)
    mock_ctx = MagicMock(spec=LangfuseTraceContext)
    mock_ctx.flush = AsyncMock(return_value=True)
    mock_tracer.start_trace.return_value = mock_ctx

    settings = Settings(langfuse_enabled=True)
    incidents = MagicMock()
    runs = MagicMock()
    security = MagicMock()
    intent = MagicMock()
    extraction = MagicMock()
    classification = MagicMock()
    priority = MagicMock()
    assignment = MagicMock()
    response = MagicMock()
    review = MagicMock()

    # Set up agents to return valid mock outputs
    security.run = AsyncMock(
        return_value=MagicMock(
            risk_score=0.1,
            risk_labels=[],
            reason_codes=["SAFE"],
            model_dump=lambda **kwargs: {"risk_score": 0.1, "reason_codes": ["SAFE"]},
        )
    )
    security.model = "gpt-5-nano"

    intent.run = AsyncMock(
        return_value=MagicMock(
            intent=Intent.FACILITY_QA,
            incident_id=None,
            reference_code=None,
            confidence=0.95,
            reason_codes=["QUERY_DETECTED"],
            model_dump=lambda **kwargs: {
                "intent": "FACILITY_QA",
                "reason_codes": ["QUERY_DETECTED"],
            },
        )
    )
    intent.model = "gpt-5-nano"
    intent.first_model_input = {"text": "What are the building opening hours?"}
    intent.final_model_input = {"text": "What are the building opening hours?"}
    intent.tool_calls = []
    intent.model_calls = 1

    response.run = AsyncMock(
        return_value=MagicMock(
            message="General response message.",
            citations=[],
            reason_codes=["ANSWER_GENERATED"],
            model_dump=lambda **kwargs: {
                "message": "General response message.",
                "citations": [],
                "reason_codes": ["ANSWER_GENERATED"],
            },
        )
    )
    response.model = "gpt-5-nano"

    review.run = AsyncMock(
        return_value=MagicMock(
            approved=True,
            issues=[],
            reason_codes=["REVIEW_PASSED"],
            model_dump=lambda **kwargs: {
                "approved": True,
                "issues": [],
                "reason_codes": ["REVIEW_PASSED"],
            },
        )
    )
    review.model = "gpt-5-nano"

    wf = FacilityWorkflow(
        settings=settings,
        incident_repository=incidents,
        workflow_repository=runs,
        security=security,
        intent=intent,
        extraction=extraction,
        classification=classification,
        priority=priority,
        assignment=assignment,
        response=response,
        review=review,
        tracer=mock_tracer,
    )

    state = await wf.run(text="What are the building opening hours?")
    assert state.outcome == "FINALIZED"

    # Verify trace started
    mock_tracer.start_trace.assert_called_once()
    assert mock_ctx.log_generation.call_count >= 2
    assert mock_ctx.log_span.call_count >= 1
    mock_ctx.end.assert_called_once()
    mock_ctx.flush.assert_called_once()
