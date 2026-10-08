from typing import Any

from app.agents.base import BaseAgent, StrictAgentModel


class ReviewOutput(StrictAgentModel):
    # Field order is the generation order under strict structured output: the model
    # names concrete defects first and only then decides, so the verdict follows the
    # findings instead of being rationalised after the fact.
    issues: list[str]
    reason_codes: list[str]
    approved: bool


class ReviewAgent(BaseAgent[ReviewOutput]):
    name = "review"
    output_schema = ReviewOutput

    def fallback(self, payload: dict[str, Any], error: Exception) -> ReviewOutput:
        del payload, error
        return ReviewOutput(
            approved=False,
            issues=["Review agent unavailable"],
            reason_codes=["HUMAN_REVIEW_REQUIRED"],
        )
