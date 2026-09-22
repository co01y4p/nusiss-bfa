import asyncio
import time
from enum import StrEnum
from typing import Any

from pydantic import Field, ValidationError

from app.agents.base import BaseAgent, StrictAgentModel
from app.llm.gateway import FunctionCallRecord, StructuredLLM
from app.monitoring.metrics import record_agent_run, record_schema_validation_failure
from app.tools.registry import ToolRegistry


class IncidentCategory(StrEnum):
    HVAC = "HVAC"
    ELECTRICAL = "ELECTRICAL"
    PLUMBING = "PLUMBING"
    LIFT = "LIFT"
    ACCESS = "ACCESS"
    GENERAL = "GENERAL"


class ClassificationOutput(StrictAgentModel):
    category: IncidentCategory
    confidence: float = Field(ge=0, le=1)
    reason_codes: list[str]


class ClassificationAgent(BaseAgent[ClassificationOutput]):
    name = "classification"
    output_schema = ClassificationOutput

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
        self.tool_calls: list[FunctionCallRecord] = []

    async def run(self, payload: dict[str, Any]) -> ClassificationOutput:
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

        available_tools = (
            registry.function_tools(caller_role="SYSTEM", names={"find_recent_incidents"})
            if registry is not None
            else []
        )

        start_time = time.perf_counter()
        try:
            async with asyncio.timeout(self.timeout_seconds):
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
            self.tool_calls = result.tool_calls
            duration = time.perf_counter() - start_time
            record_agent_run(self.name, status="success", duration_seconds=duration)
            return result.output
        except Exception as exc:
            duration = time.perf_counter() - start_time
            self.tool_calls = []
            if isinstance(exc, ValidationError):
                record_schema_validation_failure(self.name)
            record_agent_run(self.name, status="fallback", duration_seconds=duration)
            return self.fallback(payload, exc)

    def fallback(self, payload: dict[str, Any], error: Exception) -> ClassificationOutput:
        del payload, error
        return ClassificationOutput(
            category=IncidentCategory.GENERAL,
            confidence=0,
            reason_codes=["GENERAL_FALLBACK", "MANUAL_REVIEW"],
        )
