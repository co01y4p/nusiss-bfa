from typing import Any

from app.agents.base import BaseAgent, StrictAgentModel


class ResponseOutput(StrictAgentModel):
    message: str
    citations: list[str]
    reason_codes: list[str]


REFUSAL_MESSAGE = "I do not have enough approved facility information to answer that question."


class ResponseAgent(BaseAgent[ResponseOutput]):
    name = "response"
    output_schema = ResponseOutput

    async def run(self, payload: dict[str, Any]) -> ResponseOutput:
        output = await super().run(payload)
        if output.message.strip() == REFUSAL_MESSAGE:
            # A refusal draws no fact from any chunk, so it can never cite one.
            output.citations = []
        return output

    def fallback(self, payload: dict[str, Any], error: Exception) -> ResponseOutput:
        del error
        reference = payload.get("reference_code")
        message = (
            f"Your report has been saved. Reference: {reference}."
            if reference
            else "The request needs manual review."
        )
        return ResponseOutput(message=message, citations=[], reason_codes=["CONTROLLED_TEMPLATE"])
