import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ToolExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    data: Any = None
    error: str | None = None
    reason_codes: list[str] = Field(default_factory=list)


class ToolDefinition(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    name: str
    description: str
    input_schema: type[BaseModel]
    required_role: str = "PUBLIC"
    handler: Callable[..., Awaitable[Any] | Any]


class ToolRegistry:
    """Strict typed tool allow-list registry with schema validation and authorization."""

    ROLE_HIERARCHY: dict[str, int] = {
        "PUBLIC": 0,
        "MANAGER": 10,
        "SYSTEM": 20,
    }

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self,
        *,
        name: str,
        description: str,
        input_schema: type[BaseModel],
        required_role: str = "PUBLIC",
        handler: Callable[..., Awaitable[Any] | Any],
    ) -> None:
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            input_schema=input_schema,
            required_role=required_role,
            handler=handler,
        )

    def is_registered(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self, caller_role: str = "PUBLIC") -> list[dict[str, str]]:
        caller_level = self.ROLE_HIERARCHY.get(caller_role.upper(), 0)
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "required_role": tool.required_role,
            }
            for tool in self._tools.values()
            if caller_level >= self.ROLE_HIERARCHY.get(tool.required_role.upper(), 0)
        ]

    async def execute(
        self,
        name: str,
        payload: dict[str, Any],
        caller_role: str = "PUBLIC",
    ) -> ToolExecutionResult:
        if name not in self._tools:
            return ToolExecutionResult(
                success=False,
                error=f"Tool '{name}' is not in the allow-list registry",
                reason_codes=["TOOL_NOT_ALLOWLISTED", "UNKNOWN_TOOL"],
            )

        tool = self._tools[name]
        caller_level = self.ROLE_HIERARCHY.get(caller_role.upper(), 0)
        required_level = self.ROLE_HIERARCHY.get(tool.required_role.upper(), 0)

        if caller_level < required_level:
            err_msg = (
                f"Caller role '{caller_role}' does not have permission "
                f"to execute tool '{name}' (requires '{tool.required_role}')"
            )
            return ToolExecutionResult(
                success=False,
                error=err_msg,
                reason_codes=["INSUFFICIENT_TOOL_PERMISSIONS", "UNAUTHORIZED_TOOL_INVOCATION"],
            )

        try:
            validated_args = tool.input_schema.model_validate(payload)
        except ValidationError as exc:
            return ToolExecutionResult(
                success=False,
                error=f"Invalid arguments for tool '{name}': {exc.errors()}",
                reason_codes=["INVALID_TOOL_ARGUMENTS", "SCHEMA_VALIDATION_ERROR"],
            )

        try:
            if inspect.iscoroutinefunction(tool.handler):
                result = await tool.handler(validated_args)
            else:
                result = tool.handler(validated_args)

            return ToolExecutionResult(
                success=True,
                data=result,
                reason_codes=["TOOL_EXECUTION_SUCCESS"],
            )
        except Exception as exc:
            return ToolExecutionResult(
                success=False,
                error=f"Error executing tool '{name}': {str(exc)}",
                reason_codes=["TOOL_EXECUTION_FAILED"],
            )
