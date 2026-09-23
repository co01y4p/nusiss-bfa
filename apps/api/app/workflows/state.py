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
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, arbitrary_types_allowed=True
    )

    input_text: str
    supplied_location: str | None = None
    # Prior turns supplied by the client, oldest first:
    # [{"role": "user" | "assistant", "content": str}].
    history: list[dict[str, str]] = Field(default_factory=list)
    # What the agents classify: earlier occupant turns joined with the current message, so a
    # follow-up such as "level 3 pantry" is read together with the report it answers.
    effective_text: str = ""
    # Set when the occupant answered a pending offer: "CREATE_INCIDENT" or "DECLINE".
    confirm_action: str | None = None
    step_count: int = 0
    model_calls: int = 0
    incident_id: str | None = None
    reference_code: str | None = None
    outcome: str = "RUNNING"
    final_response: str = ""
    # Offer the UI should present with the reply, e.g. "shall I log this?" plus a
    # countdown. None means there is nothing to confirm.
    pending_action: dict[str, Any] | None = None
    trace: list[TraceStep] = Field(default_factory=list)
    trace_ctx: Any = Field(default=None, exclude=True)

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
