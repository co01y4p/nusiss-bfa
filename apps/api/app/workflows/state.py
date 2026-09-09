from typing import Any

from pydantic import ConfigDict, Field

from app.agents.base import StrictAgentModel


class TraceStep(StrictAgentModel):
    sequence: int
    node: str
    input: dict[str, Any] | None = None
    output: dict[str, Any]
    reason_codes: list[str] = Field(default_factory=list)


class WorkflowState(StrictAgentModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    input_text: str
    supplied_location: str | None = None
    step_count: int = 0
    model_calls: int = 0
    incident_id: str | None = None
    reference_code: str | None = None
    outcome: str = "RUNNING"
    final_response: str = ""
    trace: list[TraceStep] = Field(default_factory=list)

    def record(
        self,
        node: str,
        output: dict[str, Any],
        reason_codes: list[str],
        *,
        input: dict[str, Any] | None = None,
    ) -> None:
        self.step_count += 1
        self.trace.append(
            TraceStep(
                sequence=self.step_count,
                node=node,
                input=input,
                output=output,
                reason_codes=reason_codes,
            )
        )
