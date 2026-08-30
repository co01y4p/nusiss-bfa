import json
from typing import Any

import httpx
import pytest

from app.agents.base import StrictAgentModel
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
