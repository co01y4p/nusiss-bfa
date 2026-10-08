from typing import Any

from pydantic import Field

from app.agents.base import BaseAgent, StrictAgentModel
from app.security.prompt_injection import PromptInjectionDetector, is_benign_self_correction

QUARANTINE_THRESHOLD = 0.8
# Ceiling applied to a model-only risk score when the deterministic hazard check has
# flagged a life-safety report. Keeps the report below the quarantine threshold.
LIFE_SAFETY_RISK_CEILING = 0.5
# Same idea for a plain correction of the occupant's own earlier message.
SELF_CORRECTION_RISK_CEILING = 0.5


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
        output = self._protect_life_safety_report(payload, output)
        return self._allow_self_correction(payload, output)

    @staticmethod
    def _allow_self_correction(payload: dict[str, Any], output: SecurityOutput) -> SecurityOutput:
        """Do not quarantine "forget my earlier message" on the model's suspicion alone.

        Only reached when the deterministic heuristics found nothing. The exemption is
        narrow: it needs an explicit reference to the occupant's own earlier
        message/report/request and none of the words that target the assistant itself
        (instructions, rules, prompt, system, role, secrets, ...).
        """
        if output.risk_score < QUARANTINE_THRESHOLD:
            return output
        # BaseAgent.run turns a model failure into a fail-closed result instead of raising.
        # That means "the model did not answer", which must never be exempted.
        if "FAIL_CLOSED" in output.reason_codes or "SECURITY_AGENT_FAILURE" in output.risk_labels:
            return output
        if not is_benign_self_correction(str(payload.get("text", ""))):
            return output
        return SecurityOutput(
            risk_score=min(output.risk_score, SELF_CORRECTION_RISK_CEILING),
            risk_labels=output.risk_labels,
            reason_codes=sorted({*output.reason_codes, "SELF_CORRECTION_NOT_QUARANTINED"}),
        )

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
