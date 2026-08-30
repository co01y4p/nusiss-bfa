import json
from typing import Any, Literal

import httpx

from app.llm.gateway import OutputT
from app.llm.retry import with_transient_retries


class OpenAICompatibleStructuredLLM:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        api_style: Literal["responses", "chat_completions"] = "chat_completions",
        reasoning_effort: str = "minimal",
        max_output_tokens: int = 1024,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_style = api_style
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self.transport = transport

    async def generate(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        output_schema: type[OutputT],
        model: str,
        temperature: float = 0.0,
        timeout_seconds: float = 20.0,
    ) -> OutputT:
        if self.api_style == "responses":
            return await self._generate_responses(
                system_prompt=system_prompt,
                user_payload=user_payload,
                output_schema=output_schema,
                model=model,
                timeout_seconds=timeout_seconds,
            )
        return await self._generate_chat_completion(
            system_prompt=system_prompt,
            user_payload=user_payload,
            output_schema=output_schema,
            model=model,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
        )

    async def _generate_responses(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        output_schema: type[OutputT],
        model: str,
        timeout_seconds: float,
    ) -> OutputT:
        request_body: dict[str, Any] = {
            "model": model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": output_schema.__name__,
                    "strict": True,
                    "schema": output_schema.model_json_schema(),
                }
            },
            "reasoning": {"effort": self.reasoning_effort},
            "max_output_tokens": self.max_output_tokens,
            "store": False,
        }

        async def send() -> OutputT:
            async with httpx.AsyncClient(
                timeout=timeout_seconds, transport=self.transport
            ) as client:
                response = await client.post(
                    f"{self.base_url}/responses",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=request_body,
                )
                response.raise_for_status()
                content = self._responses_output_text(response.json())
                return output_schema.model_validate_json(content)

        return await with_transient_retries(send, retries=2)

    async def _generate_chat_completion(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        output_schema: type[OutputT],
        model: str,
        temperature: float,
        timeout_seconds: float,
    ) -> OutputT:
        request_body = {
            "model": model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": output_schema.__name__,
                    "strict": True,
                    "schema": output_schema.model_json_schema(),
                },
            },
        }

        async def send() -> OutputT:
            async with httpx.AsyncClient(
                timeout=timeout_seconds, transport=self.transport
            ) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=request_body,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                return output_schema.model_validate_json(content)

        return await with_transient_retries(send, retries=2)

    @staticmethod
    def _responses_output_text(data: dict[str, Any]) -> str:
        if data.get("status") == "incomplete":
            details = data.get("incomplete_details") or {}
            reason = details.get("reason", "unknown")
            raise RuntimeError(f"OpenAI response was incomplete: {reason}")

        for output in data.get("output", []):
            if output.get("type") != "message":
                continue
            for content in output.get("content", []):
                if content.get("type") == "refusal":
                    raise RuntimeError("OpenAI refused to produce the requested structured output")
                text = content.get("text")
                if content.get("type") == "output_text" and isinstance(text, str):
                    return text
        raise RuntimeError("OpenAI response did not contain structured output text")
