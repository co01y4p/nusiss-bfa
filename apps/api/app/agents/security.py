from typing import Any

from pydantic import Field

from app.agents.base import BaseAgent, StrictAgentModel
from app.security.prompt_injection import PromptInjectionDetector


class SecurityOutput(StrictAgentModel):
    risk_score: float = Field(ge=0, le=1)
    risk_labels: list[str]
    reason_codes: list[str]


class SecurityAgent(BaseAgent[SecurityOutput]):
    name = "security"
    output_schema = SecurityOutput

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.detector = PromptInjectionDetector()

    async def run(self, payload: dict[str, Any]) -> SecurityOutput:
        text = str(payload.get("text", ""))
        heuristic_score = self.detector.score_input(text)

        # If deterministic pattern detector detects high-risk injection, fail closed immediately
        if heuristic_score.is_high_risk:
            return SecurityOutput(
                risk_score=heuristic_score.risk_score,
                risk_labels=heuristic_score.risk_labels,
                reason_codes=heuristic_score.reason_codes,
            )

        try:
            llm_output = await super().run(payload)
            # Combine scores (take highest risk)
            combined_score = max(heuristic_score.risk_score, llm_output.risk_score)
            combined_labels = sorted(set(heuristic_score.risk_labels + llm_output.risk_labels))
            combined_reasons = sorted(set(heuristic_score.reason_codes + llm_output.reason_codes))
            return SecurityOutput(
                risk_score=combined_score,
                risk_labels=combined_labels,
                reason_codes=combined_reasons,
            )
        except Exception as exc:
            return self.fallback(payload, exc)

    def fallback(self, payload: dict[str, Any], error: Exception) -> SecurityOutput:
        del payload, error
        return SecurityOutput(
            risk_score=1.0,
            risk_labels=["SECURITY_AGENT_FAILURE"],
            reason_codes=["FAIL_CLOSED"],
        )
