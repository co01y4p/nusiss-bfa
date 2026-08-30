from enum import StrEnum
from typing import Any

from pydantic import Field

from app.agents.base import BaseAgent, StrictAgentModel


class HazardCode(StrEnum):
    FIRE = "FIRE"
    SMOKE = "SMOKE"
    GAS_SMELL = "GAS_SMELL"
    EXPOSED_LIVE_WIRE = "EXPOSED_LIVE_WIRE"
    LIFT_ENTRAPMENT = "LIFT_ENTRAPMENT"
    ACTIVE_FLOODING = "ACTIVE_FLOODING"


class ExtractionOutput(StrictAgentModel):
    summary: str = Field(min_length=1, max_length=500)
    location: str = Field(min_length=1, max_length=200)
    hazard_codes: list[HazardCode]
    missing_fields: list[str]
    reason_codes: list[str]


class ExtractionAgent(BaseAgent[ExtractionOutput]):
    name = "extraction"
    output_schema = ExtractionOutput

    def fallback(self, payload: dict[str, Any], error: Exception) -> ExtractionOutput:
        del error
        text = str(payload.get("text", ""))
        location = str(payload.get("location") or "Unspecified")
        return ExtractionOutput(
            summary=text[:500] or "Unparsed incident report",
            location=location,
            hazard_codes=[],
            missing_fields=[] if location != "Unspecified" else ["location"],
            reason_codes=["RAW_TEXT_FALLBACK"],
        )
