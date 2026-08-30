from enum import StrEnum
from typing import Any

from pydantic import Field

from app.agents.base import BaseAgent, StrictAgentModel
from app.domain.incidents.policies import determine_priority


class Priority(StrEnum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class PrioritySignalOutput(StrictAgentModel):
    priority: Priority
    confidence: float = Field(ge=0, le=1)
    reason_codes: list[str]


class PriorityDecision(StrictAgentModel):
    priority: Priority
    reason_codes: list[str]
    requires_human_review: bool


class PriorityAgent(BaseAgent[PrioritySignalOutput]):
    name = "priority"
    output_schema = PrioritySignalOutput

    def fallback(self, payload: dict[str, Any], error: Exception) -> PrioritySignalOutput:
        del payload, error
        return PrioritySignalOutput(
            priority=Priority.P3,
            confidence=0,
            reason_codes=["RULE_ENGINE_FALLBACK"],
        )

    async def decide(self, payload: dict[str, Any]) -> PriorityDecision:
        signal = await self.run(payload)
        priority, reasons, review = determine_priority(
            set(payload.get("hazard_codes", [])), signal.priority.value, signal.confidence
        )
        return PriorityDecision(
            priority=Priority(priority),
            reason_codes=[*signal.reason_codes, *reasons],
            requires_human_review=review,
        )
