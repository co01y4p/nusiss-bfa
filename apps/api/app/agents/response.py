from typing import Any

from app.agents.base import BaseAgent, StrictAgentModel


class ResponseOutput(StrictAgentModel):
    message: str
    citations: list[str]
    reason_codes: list[str]


class ResponseAgent(BaseAgent[ResponseOutput]):
    name = "response"
    output_schema = ResponseOutput

    def fallback(self, payload: dict[str, Any], error: Exception) -> ResponseOutput:
        del error
        reference = payload.get("reference_code")
        message = (
            f"Your report has been saved. Reference: {reference}."
            if reference
            else "The request needs manual review."
        )
        return ResponseOutput(message=message, citations=[], reason_codes=["CONTROLLED_TEMPLATE"])
