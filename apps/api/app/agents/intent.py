import asyncio
from enum import StrEnum
from typing import Any

from pydantic import Field, ValidationError

from app.agents.base import BaseAgent, StrictAgentModel
from app.llm.gateway import (
    FunctionCallRecord,
    StructuredLLM,
    ToolCallingError,
    ToolCallingResult,
)
from app.monitoring.metrics import (
    record_agent_retry,
    record_agent_run,
    record_schema_validation_failure,
)
from app.tools.registry import ToolRegistry


class Intent(StrEnum):
    INCIDENT_REPORT = "INCIDENT_REPORT"
    FACILITY_QA = "FACILITY_QA"
    STATUS_QUERY = "STATUS_QUERY"
    FEEDBACK = "FEEDBACK"
    OTHER = "OTHER"


class IntentOutput(StrictAgentModel):
    intent: Intent
    incident_id: str | None
    reference_code: str | None
    confidence: float = Field(ge=0, le=1)
    reason_codes: list[str]


class IntentAgent(BaseAgent[IntentOutput]):
    name = "intent"
    output_schema = IntentOutput

    def __init__(
        self,
        llm: StructuredLLM,
        *,
        model: str,
        timeout_seconds: float,
        tools: ToolRegistry | None = None,
        system_prompt: str | None = None,
    ) -> None:
        super().__init__(
            llm, model=model, timeout_seconds=timeout_seconds, system_prompt=system_prompt
        )
        self.tools = tools
        self.model_calls = 1
        self.tool_calls: list[FunctionCallRecord] = []
        self.first_model_input: dict[str, Any] = {}
        self.final_model_input: dict[str, Any] | None = None

    async def run(self, payload: dict[str, Any]) -> IntentOutput:
        registry = self.tools

        async def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            if registry is None:
                return {
                    "success": False,
                    "data": None,
                    "error": "Tool registry is unavailable",
                    "reason_codes": ["TOOL_REGISTRY_UNAVAILABLE"],
                }
            result = await registry.execute(name, arguments, caller_role="SYSTEM")
            return result.model_dump(mode="json")

        async def call_model(user_payload: dict[str, Any]) -> ToolCallingResult[IntentOutput]:
            available_tools = (
                registry.function_tools(caller_role="SYSTEM", names={"create_incident"})
                if registry is not None
                else []
            )
            return await self.llm.generate_with_tools(
                system_prompt=self.system_prompt,
                user_payload=user_payload,
                output_schema=self.output_schema,
                tools=available_tools,
                tool_executor=execute_tool,
                model=self.model,
                temperature=0.0,
                timeout_seconds=self.timeout_seconds,
                max_tool_calls=1,
            )

        start_time = asyncio.get_event_loop().time()
        try:
            async with asyncio.timeout(self.timeout_seconds):
                result = await call_model(payload)
                created = self._created_incident(result.tool_calls)

                # The model may classify this as a new incident but skip the
                # required create_incident call. Retry with a reminder, up to
                # max_attempts total, rather than silently punting the
                # occupant to manual triage after a single missed call.
                max_attempts = 3
                attempt = 1
                while (
                    created is None
                    and result.output.intent == Intent.INCIDENT_REPORT
                    and attempt < max_attempts
                ):
                    attempt += 1
                    record_agent_retry(agent="intent", reason="MISSING_TOOL_CALL")
                    retry_payload = {
                        **payload,
                        "_reminder": (
                            "Your previous turn classified this message as "
                            "INCIDENT_REPORT but did not call create_incident. "
                            "Call it now before returning your final output."
                        ),
                    }
                    retry_result = await call_model(retry_payload)
                    result = ToolCallingResult(
                        output=retry_result.output,
                        tool_calls=result.tool_calls + retry_result.tool_calls,
                        model_calls=result.model_calls + retry_result.model_calls,
                        first_model_input=result.first_model_input,
                    )
                    created = self._created_incident(result.tool_calls)

                self.model_calls = result.model_calls
                self.tool_calls = result.tool_calls
                self.first_model_input = result.first_model_input
                self.final_model_input = self._build_final_model_input(result.tool_calls)
                output = result.output
                if created is not None:
                    # Tool output is authoritative; never accept a model-invented identifier.
                    output.incident_id = created["id"]
                    output.reference_code = created["reference_code"]
                    if output.intent != Intent.INCIDENT_REPORT:
                        output.intent = Intent.INCIDENT_REPORT
                        output.reason_codes.append("TOOL_CALL_INTENT_MISMATCH")
                else:
                    output.incident_id = None
                    output.reference_code = None
                duration = asyncio.get_event_loop().time() - start_time
                record_agent_run(self.name, status="success", duration_seconds=duration)
                return output
        except ToolCallingError as exc:
            duration = asyncio.get_event_loop().time() - start_time
            self.model_calls = 2
            self.tool_calls = exc.tool_calls
            self.first_model_input = exc.tool_calls[0].model_input if exc.tool_calls else payload
            self.final_model_input = self._build_final_model_input(exc.tool_calls)
            created = self._created_incident(exc.tool_calls)
            if created is not None:
                record_agent_run(self.name, status="fallback", duration_seconds=duration)
                return IntentOutput(
                    intent=Intent.INCIDENT_REPORT,
                    incident_id=created["id"],
                    reference_code=created["reference_code"],
                    confidence=0,
                    reason_codes=["TOOL_SUCCEEDED_FINAL_MODEL_OUTPUT_FAILED"],
                )
            record_agent_run(self.name, status="fallback", duration_seconds=duration)
            return self.fallback(payload, exc)
        except Exception as exc:
            duration = asyncio.get_event_loop().time() - start_time
            if isinstance(exc, ValidationError):
                record_schema_validation_failure(self.name)
            self.model_calls = 1
            self.tool_calls = []
            self.first_model_input = payload
            self.final_model_input = None
            record_agent_run(self.name, status="fallback", duration_seconds=duration)
            return self.fallback(payload, exc)

    @staticmethod
    def _build_final_model_input(
        tool_calls: list[FunctionCallRecord],
    ) -> dict[str, Any] | None:
        if not tool_calls:
            return None
        return {
            "original_input": tool_calls[0].model_input,
            "function_calls": [
                {
                    "call_id": call.call_id,
                    "name": call.name,
                    "arguments": call.arguments,
                }
                for call in tool_calls
            ],
            "function_call_outputs": [
                {"call_id": call.call_id, "output": call.output} for call in tool_calls
            ],
        }

    @staticmethod
    def _created_incident(tool_calls: list[FunctionCallRecord]) -> dict[str, str] | None:
        # Prefer the most recent successful call: a retry may follow an earlier
        # failed or skipped attempt.
        for call in reversed(tool_calls):
            if call.name != "create_incident":
                continue
            created = call.output.get("data")
            if (
                call.output.get("success") is True
                and isinstance(created, dict)
                and isinstance(created.get("id"), str)
                and isinstance(created.get("reference_code"), str)
            ):
                return {"id": created["id"], "reference_code": created["reference_code"]}
        return None

    def fallback(self, payload: dict[str, Any], error: Exception) -> IntentOutput:
        del payload, error
        return IntentOutput(
            intent=Intent.OTHER,
            incident_id=None,
            reference_code=None,
            confidence=0,
            reason_codes=["MANUAL_TRIAGE"],
        )
