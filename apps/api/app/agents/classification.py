from enum import StrEnum
from typing import Any

from pydantic import Field

from app.agents.base import BaseAgent, StrictAgentModel


class IncidentCategory(StrEnum):
    HVAC = "HVAC"
    ELECTRICAL = "ELECTRICAL"
    PLUMBING = "PLUMBING"
    LIFT = "LIFT"
    ACCESS = "ACCESS"
    GENERAL = "GENERAL"


class ClassificationOutput(StrictAgentModel):
    category: IncidentCategory
    confidence: float = Field(ge=0, le=1)
    reason_codes: list[str]


class ClassificationAgent(BaseAgent[ClassificationOutput]):
    name = "classification"
    output_schema = ClassificationOutput

    def fallback(self, payload: dict[str, Any], error: Exception) -> ClassificationOutput:
        del payload, error
        return ClassificationOutput(
            category=IncidentCategory.GENERAL,
            confidence=0,
            reason_codes=["GENERAL_FALLBACK", "MANUAL_REVIEW"],
        )
