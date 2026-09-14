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
