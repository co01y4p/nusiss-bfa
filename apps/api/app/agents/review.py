from typing import Any

from app.agents.base import BaseAgent, StrictAgentModel


class ReviewOutput(StrictAgentModel):
    approved: bool
    issues: list[str]
    reason_codes: list[str]


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
