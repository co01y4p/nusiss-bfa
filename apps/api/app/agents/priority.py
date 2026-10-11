from enum import StrEnum
from typing import Any

from pydantic import Field

from app.agents.base import BaseAgent, StrictAgentModel
from app.domain.incidents.policies import detect_critical_hazards, determine_priority


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
        # Extraction can propose hazards the text does not support (a dripping tap
        # tagged EXPOSED_LIVE_WIRE). Only text-confirmed codes are presented as
        # hazards; the rest are marked as unconfirmed suspicions for the model to weigh.
        proposed = {str(code) for code in payload.get("hazard_codes", [])}
        confirmed = detect_critical_hazards(str(payload.get("text", "")))
        signal = await self.run(
            {
                **payload,
                "hazard_codes": sorted(proposed & confirmed),
                "suspected_hazards": sorted(proposed - confirmed),
            }
        )
        # A model suspicion of ACTIVE_FLOODING cannot by itself unlock P1: its everyday
        # triggers (water, floor, leaking) are also ordinary plumbing faults, and a heavy
        # pipe leak described in dialect was escalated to P1 on that suspicion alone. It
        # still reaches P1 through the deterministic text rule (flood/flooded/flooding),
        # and an unconfirmed model P1 is capped at P2 and sent for manager review.
        policy_hazards = confirmed | (proposed - {"ACTIVE_FLOODING"})
        priority, reasons, review = determine_priority(
            policy_hazards,
            signal.priority.value,
            signal.confidence,
            text=str(payload.get("text", "")),
        )
        return PriorityDecision(
            priority=Priority(priority),
            reason_codes=[*signal.reason_codes, *reasons],
            requires_human_review=review,
        )
