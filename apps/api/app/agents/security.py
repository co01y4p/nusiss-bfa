from typing import Any

from pydantic import Field

from app.agents.base import BaseAgent, StrictAgentModel
from app.security.prompt_injection import PromptInjectionDetector

QUARANTINE_THRESHOLD = 0.8
# Ceiling applied to a model-only risk score when the deterministic hazard check has
# flagged a life-safety report. Keeps the report below the quarantine threshold.
LIFE_SAFETY_RISK_CEILING = 0.5


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
            output = SecurityOutput(
                risk_score=combined_score,
                risk_labels=combined_labels,
                reason_codes=combined_reasons,
            )
        except Exception as exc:
            output = self.fallback(payload, exc)
        return self._protect_life_safety_report(payload, output)

    @staticmethod
    def _protect_life_safety_report(
        payload: dict[str, Any], output: SecurityOutput
    ) -> SecurityOutput:
        """Never quarantine a flagged hazard report on the model's judgement alone.

        Only reached when the deterministic injection heuristics passed. Quarantining a
        gas-smell or fire report delays help for someone who may be in danger, which is a
        worse failure than letting a model-only suspicion through to the downstream
        output validator and review gate.
        """
        if not payload.get("critical_hazard_detected") or output.risk_score < QUARANTINE_THRESHOLD:
            return output
        return SecurityOutput(
            risk_score=min(output.risk_score, LIFE_SAFETY_RISK_CEILING),
            risk_labels=output.risk_labels,
            reason_codes=sorted({*output.reason_codes, "LIFE_SAFETY_REPORT_NOT_QUARANTINED"}),
        )

    def fallback(self, payload: dict[str, Any], error: Exception) -> SecurityOutput:
        del payload, error
        return SecurityOutput(
            risk_score=1.0,
            risk_labels=["SECURITY_AGENT_FAILURE"],
            reason_codes=["FAIL_CLOSED"],
        )
