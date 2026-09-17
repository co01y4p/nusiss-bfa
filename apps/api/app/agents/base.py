import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

from app.llm.gateway import StructuredLLM
from app.monitoring.metrics import (
    record_agent_run,
    record_schema_validation_failure,
)
from app.prompts import load_prompt


class StrictAgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


AgentOutputT = TypeVar("AgentOutputT", bound=StrictAgentModel)


class BaseAgent(ABC, Generic[AgentOutputT]):  # noqa: UP046
    name: str
    output_schema: type[AgentOutputT]

    def __init__(
        self,
        llm: StructuredLLM,
        *,
        model: str,
        timeout_seconds: float,
        system_prompt: str | None = None,
    ) -> None:
        self.llm = llm
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.system_prompt = (
            system_prompt.strip()
            if system_prompt and system_prompt.strip()
            else load_prompt(self.name)
        )

    async def run(self, payload: dict[str, Any]) -> AgentOutputT:
        start_time = time.perf_counter()
        try:
            async with asyncio.timeout(self.timeout_seconds):
                output = await self.llm.generate(
                    system_prompt=self.system_prompt,
                    user_payload=payload,
                    output_schema=self.output_schema,
                    model=self.model,
                    temperature=0.0,
                    timeout_seconds=self.timeout_seconds,
                )
            duration = time.perf_counter() - start_time
            record_agent_run(self.name, status="success", duration_seconds=duration)
            return output
        except Exception as exc:
            duration = time.perf_counter() - start_time
            if isinstance(exc, ValidationError):
                record_schema_validation_failure(self.name)
            record_agent_run(self.name, status="fallback", duration_seconds=duration)
            return self.fallback(payload, exc)

    @abstractmethod
    def fallback(self, payload: dict[str, Any], error: Exception) -> AgentOutputT:
        raise NotImplementedError
