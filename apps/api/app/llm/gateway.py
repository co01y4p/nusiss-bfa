from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

OutputT = TypeVar("OutputT", bound=BaseModel)


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
