import json
from typing import Any

import httpx

from app.llm.gateway import OutputT
from app.llm.retry import with_transient_retries


class OpenAICompatibleStructuredLLM:
    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

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
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=request_body,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                return output_schema.model_validate_json(content)

        return await with_transient_retries(send, retries=2)
