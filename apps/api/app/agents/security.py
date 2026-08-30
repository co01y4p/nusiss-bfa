from typing import Any

from pydantic import Field

from app.agents.base import BaseAgent, StrictAgentModel


class SecurityOutput(StrictAgentModel):
    risk_score: float = Field(ge=0, le=1)
    risk_labels: list[str]
    reason_codes: list[str]


class SecurityAgent(BaseAgent[SecurityOutput]):
    name = "security"
    output_schema = SecurityOutput

    def fallback(self, payload: dict[str, Any], error: Exception) -> SecurityOutput:
        del payload, error
        return SecurityOutput(
            risk_score=1.0,
            risk_labels=["SECURITY_AGENT_FAILURE"],
            reason_codes=["FAIL_CLOSED"],
        )
