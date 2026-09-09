import asyncio
from enum import StrEnum
from typing import Any

from pydantic import Field

from app.agents.base import BaseAgent, StrictAgentModel
from app.llm.gateway import FunctionCallRecord, StructuredLLM, ToolCallingError
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

        try:
            async with asyncio.timeout(self.timeout_seconds):
                available_tools = (
                    registry.function_tools(caller_role="SYSTEM", names={"create_incident"})
                    if registry is not None
                    else []
                )
                result = await self.llm.generate_with_tools(
                    system_prompt=self.system_prompt,
                    user_payload=payload,
                    output_schema=self.output_schema,
                    tools=available_tools,
                    tool_executor=execute_tool,
                    model=self.model,
                    temperature=0.0,
                    timeout_seconds=self.timeout_seconds,
                    max_tool_calls=1,
                )
                self.model_calls = result.model_calls
                self.tool_calls = result.tool_calls
                self.first_model_input = result.first_model_input
                output = result.output
                created = self._created_incident(result.tool_calls)
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
                return output
        except ToolCallingError as exc:
            self.model_calls = 2
            self.tool_calls = exc.tool_calls
            self.first_model_input = exc.tool_calls[0].model_input if exc.tool_calls else payload
            created = self._created_incident(exc.tool_calls)
            if created is not None:
                return IntentOutput(
                    intent=Intent.INCIDENT_REPORT,
                    incident_id=created["id"],
                    reference_code=created["reference_code"],
                    confidence=0,
                    reason_codes=["TOOL_SUCCEEDED_FINAL_MODEL_OUTPUT_FAILED"],
                )
            return self.fallback(payload, exc)
        except Exception as exc:
            self.model_calls = 1
            self.tool_calls = []
            self.first_model_input = payload
            return self.fallback(payload, exc)

    @staticmethod
    def _created_incident(tool_calls: list[FunctionCallRecord]) -> dict[str, str] | None:
        create_call = next((call for call in tool_calls if call.name == "create_incident"), None)
        created = create_call.output.get("data") if create_call else None
        if (
            create_call
            and create_call.output.get("success") is True
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
