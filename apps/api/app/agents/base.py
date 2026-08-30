import asyncio
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

from app.llm.gateway import StructuredLLM
from app.prompts import load_prompt


class StrictAgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


AgentOutputT = TypeVar("AgentOutputT", bound=StrictAgentModel)


class BaseAgent(ABC, Generic[AgentOutputT]):  # noqa: UP046
    name: str
    output_schema: type[AgentOutputT]

    def __init__(self, llm: StructuredLLM, *, model: str, timeout_seconds: float) -> None:
        self.llm = llm
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.system_prompt = load_prompt(self.name)

    async def run(self, payload: dict[str, Any]) -> AgentOutputT:
        try:
            async with asyncio.timeout(self.timeout_seconds):
                return await self.llm.generate(
                    system_prompt=self.system_prompt,
                    user_payload=payload,
                    output_schema=self.output_schema,
                    model=self.model,
                    temperature=0.0,
                    timeout_seconds=self.timeout_seconds,
                )
        except Exception as exc:
            return self.fallback(payload, exc)

    @abstractmethod
    def fallback(self, payload: dict[str, Any], error: Exception) -> AgentOutputT:
        raise NotImplementedError
