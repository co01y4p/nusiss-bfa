from enum import StrEnum
from typing import Any

from app.agents.base import BaseAgent, StrictAgentModel


class Team(StrEnum):
    HVAC_TEAM = "HVAC_TEAM"
    ELECTRICAL_TEAM = "ELECTRICAL_TEAM"
    PLUMBING_TEAM = "PLUMBING_TEAM"
    LIFT_TEAM = "LIFT_TEAM"
    SECURITY_TEAM = "SECURITY_TEAM"
    FACILITIES_DESK = "FACILITIES_DESK"


class AssignmentOutput(StrictAgentModel):
    team: Team
    reason_codes: list[str]


class AssignmentAgent(BaseAgent[AssignmentOutput]):
    name = "assignment"
    output_schema = AssignmentOutput

    def fallback(self, payload: dict[str, Any], error: Exception) -> AssignmentOutput:
        del payload, error
        return AssignmentOutput(team=Team.FACILITIES_DESK, reason_codes=["UNASSIGNED_FALLBACK"])
