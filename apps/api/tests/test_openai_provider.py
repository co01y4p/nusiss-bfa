import json
from typing import Any

import httpx
import pytest

from app.agents.base import StrictAgentModel
from app.llm.gateway import FunctionTool
from app.llm.providers.openai_compatible import OpenAICompatibleStructuredLLM


class ExampleOutput(StrictAgentModel):
    label: str
    confidence: float


@pytest.mark.asyncio
async def test_openai_responses_uses_structured_output_without_temperature() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {"type": "reasoning", "summary": []},
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"label":"INCIDENT_REPORT","confidence":0.98}',
                            }
                        ],
                    },
                ],
            },
        )

    provider = OpenAICompatibleStructuredLLM(
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        api_style="responses",
        reasoning_effort="minimal",
        max_output_tokens=512,
        transport=httpx.MockTransport(handler),
    )

    result = await provider.generate(
        system_prompt="Classify the request.",
        user_payload={"text": "The lobby light is broken."},
        output_schema=ExampleOutput,
        model="gpt-5-nano",
    )

    body = captured["body"]
    assert result == ExampleOutput(label="INCIDENT_REPORT", confidence=0.98)
    assert captured["path"] == "/v1/responses"
    assert captured["authorization"] == "Bearer test-key"
    assert "temperature" not in body
    assert body["reasoning"] == {"effort": "minimal"}
    assert body["max_output_tokens"] == 512
    assert body["store"] is False
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["strict"] is True
    assert body["text"]["format"]["schema"]["additionalProperties"] is False


@pytest.mark.asyncio
async def test_openai_responses_rejects_incomplete_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
                "output": [],
            },
        )

    provider = OpenAICompatibleStructuredLLM(
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        api_style="responses",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(RuntimeError, match="max_output_tokens"):
        await provider.generate(
            system_prompt="Classify the request.",
            user_payload={"text": "The lobby light is broken."},
            output_schema=ExampleOutput,
            model="gpt-5-nano",
        )


@pytest.mark.asyncio
async def test_openai_responses_executes_function_and_returns_output_to_model() -> None:
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "output": [
                        {"type": "reasoning", "summary": []},
                        {
                            "type": "function_call",
                            "call_id": "call-create-1",
                            "name": "create_incident",
                            "arguments": json.dumps(
                                {
                                    "description": "The lobby light is broken.",
                                    "location": "Lobby",
                                }
                            ),
                        },
                    ],
                },
            )
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
                                "text": '{"label":"INCIDENT_REPORT","confidence":0.98}',
                            }
                        ],
                    }
                ],
            },
        )

    async def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        assert name == "create_incident"
        assert arguments["location"] == "Lobby"
        return {
            "success": True,
            "data": {"id": "incident-123", "reference_code": "BFA-TEST123"},
            "error": None,
            "reason_codes": ["TOOL_EXECUTION_SUCCESS"],
        }

    provider = OpenAICompatibleStructuredLLM(
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        api_style="responses",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.generate_with_tools(
        system_prompt="Classify and create incidents.",
        user_payload={"text": "The lobby light is broken.", "location": "Lobby"},
        output_schema=ExampleOutput,
        tools=[
            FunctionTool(
                name="create_incident",
                description="Create an incident",
                parameters={
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "location": {"type": "string"},
                    },
                    "required": ["description", "location"],
                    "additionalProperties": False,
                },
            )
        ],
        tool_executor=execute_tool,
        model="gpt-5-nano",
    )

    assert result.output == ExampleOutput(label="INCIDENT_REPORT", confidence=0.98)
    assert result.model_calls == 2
    assert result.tool_calls[0].output["data"]["id"] == "incident-123"
    assert result.tool_calls[0].model_input == {
        "text": "The lobby light is broken.",
        "location": "Lobby",
    }
    assert requests[0]["tools"][0]["name"] == "create_incident"
    assert requests[0]["tools"][0]["strict"] is True
    assert requests[0]["parallel_tool_calls"] is False
    assert requests[1]["tool_choice"] == "none"
    function_output = requests[1]["input"][-1]
    assert function_output["type"] == "function_call_output"
    assert function_output["call_id"] == "call-create-1"
    assert json.loads(function_output["output"])["data"]["id"] == "incident-123"


@pytest.mark.asyncio
async def test_openai_reuses_persistent_http_client() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"label":"INCIDENT_REPORT","confidence":0.99}',
                        }
                    }
                ]
            },
        )

    provider = OpenAICompatibleStructuredLLM(
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )

    client1 = provider._get_client()
    await provider.generate(
        system_prompt="Classify",
        user_payload={"text": "First call"},
        output_schema=ExampleOutput,
        model="gpt-4o-mini",
    )
    client2 = provider._get_client()

    assert client1 is client2
    assert not client1.is_closed

    await provider.generate(
        system_prompt="Classify",
        user_payload={"text": "Second call"},
        output_schema=ExampleOutput,
        model="gpt-4o-mini",
    )
    assert call_count == 2

    await provider.aclose()
    assert client1.is_closed


@pytest.mark.asyncio
async def test_stalled_attempt_times_out_early_and_is_retried() -> None:
    timeouts: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        timeouts.append(request.extensions["timeout"]["read"])
        if len(timeouts) == 1:
            raise httpx.ReadTimeout("stalled", request=request)
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": '{"label":"OK","confidence":1}'}
                        ],
                    }
                ]
            },
        )

    provider = OpenAICompatibleStructuredLLM(
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        api_style="responses",
        attempt_timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )

    result = await provider.generate(
        system_prompt="Classify the request.",
        user_payload={"text": "The lobby light is broken."},
        output_schema=ExampleOutput,
        model="gpt-5-nano",
        timeout_seconds=30,
    )

    assert result == ExampleOutput(label="OK", confidence=1)
    # Each attempt is capped below the agent budget, so the stall is retried.
    assert timeouts == [5, 5]


def _responses_provider(
    captured: list[dict[str, Any]], **kwargs: Any
) -> OpenAICompatibleStructuredLLM:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": '{"label":"OK","confidence":1}'}
                        ],
                    }
                ]
            },
        )

    return OpenAICompatibleStructuredLLM(
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        api_style="responses",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_per_call_reasoning_effort_overrides_the_provider_default() -> None:
    bodies: list[dict[str, Any]] = []
    provider = _responses_provider(bodies, reasoning_effort="minimal")
    common: dict[str, Any] = {
        "system_prompt": "Classify.",
        "user_payload": {"text": "x"},
        "output_schema": ExampleOutput,
        "model": "gpt-5-nano",
    }

    await provider.generate(**common)
    await provider.generate(**common, reasoning_effort="low")

    assert [body["reasoning"] for body in bodies] == [{"effort": "minimal"}, {"effort": "low"}]


@pytest.mark.asyncio
async def test_reasoning_effort_reaches_the_tool_calling_request_without_tools() -> None:
    bodies: list[dict[str, Any]] = []
    provider = _responses_provider(bodies, reasoning_effort="minimal")

    await provider.generate_with_tools(
        system_prompt="Classify.",
        user_payload={"text": "x"},
        output_schema=ExampleOutput,
        tools=[],
        tool_executor=lambda name, arguments: {},  # type: ignore[arg-type,return-value]
        model="gpt-5-nano",
        reasoning_effort="low",
    )

    assert bodies[0]["reasoning"] == {"effort": "low"}
