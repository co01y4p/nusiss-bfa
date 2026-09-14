import json
from typing import Any, Literal

import httpx

from app.llm.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError, default_circuit_breaker
from app.llm.gateway import (
    FunctionCallRecord,
    FunctionTool,
    OutputT,
    ToolCallingError,
    ToolCallingResult,
    ToolExecutor,
)
from app.llm.retry import with_transient_retries
from app.security.pii_redaction import redact_payload


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
        circuit_breaker: CircuitBreaker | None = None,
        redact_pii_inputs: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_style = api_style
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self.transport = transport
        self.circuit_breaker = circuit_breaker or default_circuit_breaker
        self.redact_pii_inputs = redact_pii_inputs

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
        if not self.circuit_breaker.allow_request():
            raise CircuitBreakerOpenError(
                "LLM provider circuit breaker is OPEN due to repeated failures"
            )

        sanitized_payload = redact_payload(user_payload) if self.redact_pii_inputs else user_payload

        try:
            if self.api_style == "responses":
                result = await self._generate_responses(
                    system_prompt=system_prompt,
                    user_payload=sanitized_payload,
                    output_schema=output_schema,
                    model=model,
                    timeout_seconds=timeout_seconds,
                )
            else:
                result = await self._generate_chat_completion(
                    system_prompt=system_prompt,
                    user_payload=sanitized_payload,
                    output_schema=output_schema,
                    model=model,
                    temperature=temperature,
                    timeout_seconds=timeout_seconds,
                )
            self.circuit_breaker.record_success()
            return result
        except Exception:
            self.circuit_breaker.record_failure()
            raise

    async def generate_with_tools(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        output_schema: type[OutputT],
        tools: list[FunctionTool],
        tool_executor: ToolExecutor,
        model: str,
        temperature: float = 0.0,
        timeout_seconds: float = 20.0,
        max_tool_calls: int = 1,
    ) -> ToolCallingResult[OutputT]:
        if not tools:
            sanitized_payload = (
                redact_payload(user_payload) if self.redact_pii_inputs else user_payload
            )
            output = await self.generate(
                system_prompt=system_prompt,
                user_payload=user_payload,
                output_schema=output_schema,
                model=model,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
            )
            return ToolCallingResult(
                output=output,
                tool_calls=[],
                model_calls=1,
                first_model_input=sanitized_payload,
            )
        if not self.circuit_breaker.allow_request():
            raise CircuitBreakerOpenError(
                "LLM provider circuit breaker is OPEN due to repeated failures"
            )

        sanitized_payload = redact_payload(user_payload) if self.redact_pii_inputs else user_payload
        try:
            if self.api_style == "responses":
                result = await self._generate_responses_with_tools(
                    system_prompt=system_prompt,
                    user_payload=sanitized_payload,
                    output_schema=output_schema,
                    tools=tools,
                    tool_executor=tool_executor,
                    model=model,
                    timeout_seconds=timeout_seconds,
                    max_tool_calls=max_tool_calls,
                )
            else:
                result = await self._generate_chat_completion_with_tools(
                    system_prompt=system_prompt,
                    user_payload=sanitized_payload,
                    output_schema=output_schema,
                    tools=tools,
                    tool_executor=tool_executor,
                    model=model,
                    temperature=temperature,
                    timeout_seconds=timeout_seconds,
                    max_tool_calls=max_tool_calls,
                )
            self.circuit_breaker.record_success()
            return result
        except Exception:
            self.circuit_breaker.record_failure()
            raise

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

    async def _generate_responses_with_tools(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        output_schema: type[OutputT],
        tools: list[FunctionTool],
        tool_executor: ToolExecutor,
        model: str,
        timeout_seconds: float,
        max_tool_calls: int,
    ) -> ToolCallingResult[OutputT]:
        input_items: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload)},
        ]
        request_body: dict[str, Any] = {
            "model": model,
            "input": input_items,
            "tools": [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                    "strict": tool.strict,
                }
                for tool in tools
            ],
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "text": self._responses_text_format(output_schema),
            "reasoning": {"effort": self.reasoning_effort},
            "max_output_tokens": self.max_output_tokens,
            "store": False,
        }

        first = await self._post_json(
            path="responses", body=request_body, timeout_seconds=timeout_seconds
        )
        self._check_responses_status(first)
        function_calls = [
            item for item in first.get("output", []) if item.get("type") == "function_call"
        ]
        if len(function_calls) > max_tool_calls:
            raise RuntimeError("Model exceeded the configured function-call limit")
        if not function_calls:
            return ToolCallingResult(
                output=output_schema.model_validate_json(self._responses_output_text(first)),
                tool_calls=[],
                model_calls=1,
                first_model_input=user_payload,
            )

        records: list[FunctionCallRecord] = []
        follow_up_input = [*input_items, *first.get("output", [])]
        for item in function_calls:
            name = item.get("name")
            call_id = item.get("call_id")
            if not isinstance(name, str) or not isinstance(call_id, str):
                raise RuntimeError("Model returned an invalid function call")
            arguments = json.loads(item.get("arguments", "{}"))
            if not isinstance(arguments, dict):
                raise RuntimeError("Function arguments must be a JSON object")
            tool_output = await tool_executor(name, arguments)
            records.append(
                FunctionCallRecord(
                    call_id=call_id,
                    name=name,
                    model_input=user_payload,
                    arguments=arguments,
                    output=tool_output,
                )
            )
            follow_up_input.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(tool_output),
                }
            )

        follow_up_body = {
            **request_body,
            "input": follow_up_input,
            "tool_choice": "none",
        }
        try:
            final = await self._post_json(
                path="responses", body=follow_up_body, timeout_seconds=timeout_seconds
            )
            output = output_schema.model_validate_json(self._responses_output_text(final))
        except Exception as exc:
            raise ToolCallingError(
                "Final model response failed after function execution", tool_calls=records
            ) from exc
        return ToolCallingResult(
            output=output,
            tool_calls=records,
            model_calls=2,
            first_model_input=user_payload,
        )

    async def _generate_chat_completion_with_tools(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        output_schema: type[OutputT],
        tools: list[FunctionTool],
        tool_executor: ToolExecutor,
        model: str,
        temperature: float,
        timeout_seconds: float,
        max_tool_calls: int,
    ) -> ToolCallingResult[OutputT]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload)},
        ]
        request_body: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "messages": messages,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                        "strict": tool.strict,
                    },
                }
                for tool in tools
            ],
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "response_format": self._chat_response_format(output_schema),
        }
        first = await self._post_json(
            path="chat/completions", body=request_body, timeout_seconds=timeout_seconds
        )
        message = first["choices"][0]["message"]
        function_calls = message.get("tool_calls") or []
        if len(function_calls) > max_tool_calls:
            raise RuntimeError("Model exceeded the configured function-call limit")
        if not function_calls:
            return ToolCallingResult(
                output=output_schema.model_validate_json(message["content"]),
                tool_calls=[],
                model_calls=1,
                first_model_input=user_payload,
            )

        records: list[FunctionCallRecord] = []
        follow_up_messages = [*messages, message]
        for item in function_calls:
            function = item.get("function") or {}
            name = function.get("name")
            call_id = item.get("id")
            if not isinstance(name, str) or not isinstance(call_id, str):
                raise RuntimeError("Model returned an invalid function call")
            arguments = json.loads(function.get("arguments", "{}"))
            if not isinstance(arguments, dict):
                raise RuntimeError("Function arguments must be a JSON object")
            tool_output = await tool_executor(name, arguments)
            records.append(
                FunctionCallRecord(
                    call_id=call_id,
                    name=name,
                    model_input=user_payload,
                    arguments=arguments,
                    output=tool_output,
                )
            )
            follow_up_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(tool_output),
                }
            )

        try:
            final = await self._post_json(
                path="chat/completions",
                body={
                    **request_body,
                    "messages": follow_up_messages,
                    "tool_choice": "none",
                },
                timeout_seconds=timeout_seconds,
            )
            content = final["choices"][0]["message"]["content"]
            output = output_schema.model_validate_json(content)
        except Exception as exc:
            raise ToolCallingError(
                "Final model response failed after function execution", tool_calls=records
            ) from exc
        return ToolCallingResult(
            output=output,
            tool_calls=records,
            model_calls=2,
            first_model_input=user_payload,
        )

    async def _post_json(
        self, *, path: str, body: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        async def send() -> dict[str, Any]:
            async with httpx.AsyncClient(
                timeout=timeout_seconds, transport=self.transport
            ) as client:
                response = await client.post(
                    f"{self.base_url}/{path}",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=body,
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                return data

        return await with_transient_retries(send, retries=2)

    @staticmethod
    def _responses_text_format(output_schema: type[OutputT]) -> dict[str, Any]:
        return {
            "format": {
                "type": "json_schema",
                "name": output_schema.__name__,
                "strict": True,
                "schema": output_schema.model_json_schema(),
            }
        }

    @staticmethod
    def _chat_response_format(output_schema: type[OutputT]) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": output_schema.__name__,
                "strict": True,
                "schema": output_schema.model_json_schema(),
            },
        }

    @staticmethod
    def _check_responses_status(data: dict[str, Any]) -> None:
        if data.get("status") == "incomplete":
            details = data.get("incomplete_details") or {}
            reason = details.get("reason", "unknown")
            raise RuntimeError(f"OpenAI response was incomplete: {reason}")

    @staticmethod
    def _responses_output_text(data: dict[str, Any]) -> str:
        OpenAICompatibleStructuredLLM._check_responses_status(data)

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
