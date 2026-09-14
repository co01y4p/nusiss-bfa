from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar

from pydantic import BaseModel

OutputT = TypeVar("OutputT", bound=BaseModel)
ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class FunctionTool:
    name: str
    description: str
    parameters: dict[str, Any]
    strict: bool = True


@dataclass(frozen=True)
class FunctionCallRecord:
    call_id: str
    name: str
    model_input: dict[str, Any]
    arguments: dict[str, Any]
    output: dict[str, Any]


class ToolCallingError(RuntimeError):
    """A model turn failed after one or more side-effecting tools completed."""

    def __init__(self, message: str, *, tool_calls: list[FunctionCallRecord]) -> None:
        super().__init__(message)
        self.tool_calls = tool_calls


@dataclass(frozen=True)
class ToolCallingResult(Generic[OutputT]):  # noqa: UP046
    output: OutputT
    tool_calls: list[FunctionCallRecord]
    model_calls: int
    first_model_input: dict[str, Any]


class StructuredLLM(Protocol):
    async def generate(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        output_schema: type[OutputT],
        model: str,
        temperature: float = 0.0,
        timeout_seconds: float = 20.0,
    ) -> OutputT: ...

    async def generate_with_tools(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        output_schema: type[OutputT],
        tools: list[FunctionTool],
        tool_executor: ToolExecutor,
        model: str,
        temperature: float = 0.0,
        timeout_seconds: float = 20.0,
        max_tool_calls: int = 1,
    ) -> ToolCallingResult[OutputT]: ...
