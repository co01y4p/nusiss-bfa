from enum import StrEnum
from typing import Any

from pydantic import Field

from app.agents.base import BaseAgent, StrictAgentModel


class Intent(StrEnum):
    INCIDENT_REPORT = "INCIDENT_REPORT"
    FACILITY_QA = "FACILITY_QA"
    STATUS_QUERY = "STATUS_QUERY"
    FEEDBACK = "FEEDBACK"
    OTHER = "OTHER"


class IntentTool(StrEnum):
    CREATE_INCIDENT = "create_incident"


class IntentOutput(StrictAgentModel):
    intent: Intent
    tool_name: IntentTool | None
    confidence: float = Field(ge=0, le=1)
    reason_codes: list[str]


class IntentAgent(BaseAgent[IntentOutput]):
    name = "intent"
    output_schema = IntentOutput

    def fallback(self, payload: dict[str, Any], error: Exception) -> IntentOutput:
        del payload, error
        return IntentOutput(
            intent=Intent.OTHER,
            tool_name=None,
            confidence=0,
            reason_codes=["MANUAL_TRIAGE"],
        )
