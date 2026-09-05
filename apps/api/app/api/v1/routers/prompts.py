import time
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.assignment import AssignmentAgent
from app.agents.classification import ClassificationAgent
from app.agents.extraction import ExtractionAgent
from app.agents.intent import IntentAgent
from app.agents.priority import PriorityAgent
from app.agents.response import ResponseAgent
from app.agents.review import ReviewAgent
from app.agents.security import SecurityAgent
from app.api.v1.routers.assistant import build_llm
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.prompts import AGENT_METADATA
from app.repositories.postgres.prompts import SqlAlchemyPromptRepository

router = APIRouter(prefix="/prompts", tags=["prompts"])

AGENT_CLASSES: dict[str, type] = {
    "security": SecurityAgent,
    "intent": IntentAgent,
    "extraction": ExtractionAgent,
    "classification": ClassificationAgent,
    "priority": PriorityAgent,
    "assignment": AssignmentAgent,
    "response": ResponseAgent,
    "review": ReviewAgent,
}


class PromptSummary(BaseModel):
    name: str
    title: str
    role: str
    description: str
    default_model: str
    output_schema_summary: str
    sample_input: dict[str, Any]
    system_prompt: str
    default_prompt: str
    is_customized: bool
    version: str
    updated_at: datetime | None
    change_summary: str | None
    char_count: int
    line_count: int


class PromptListResponse(BaseModel):
    agents: list[PromptSummary]
    total_count: int
    customized_count: int


class UpdatePromptRequest(BaseModel):
    system_prompt: str = Field(min_length=10, max_length=50000)
    change_summary: str | None = Field(default=None, max_length=255)


class TestPromptRequest(BaseModel):
    system_prompt: str | None = Field(default=None, max_length=50000)
    test_input: dict[str, Any] = Field(default_factory=dict)


class TestPromptResponse(BaseModel):
    status: str
    agent_name: str
    model: str
    latency_ms: int
    output: dict[str, Any]
    schema_name: str


@router.get("", response_model=PromptListResponse)
def list_prompts(db: Annotated[Session, Depends(get_db)]) -> PromptListResponse:
    repo = SqlAlchemyPromptRepository(db)
    agents_data = repo.get_all_prompts()
    customized = sum(1 for a in agents_data if a["is_customized"])
    return PromptListResponse(
        agents=[PromptSummary(**item) for item in agents_data],
        total_count=len(agents_data),
        customized_count=customized,
    )


@router.get("/{agent_name}", response_model=PromptSummary)
def get_prompt(agent_name: str, db: Annotated[Session, Depends(get_db)]) -> PromptSummary:
    if agent_name not in AGENT_METADATA:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown agent: {agent_name}. Valid agents: {list(AGENT_METADATA.keys())}",
        )
    repo = SqlAlchemyPromptRepository(db)
    agents_data = repo.get_all_prompts()
    target = next((a for a in agents_data if a["name"] == agent_name), None)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent prompt not found")
    return PromptSummary(**target)


@router.patch("/{agent_name}", response_model=PromptSummary)
def update_prompt(
    agent_name: str,
    payload: UpdatePromptRequest,
    db: Annotated[Session, Depends(get_db)],
) -> PromptSummary:
    if agent_name not in AGENT_METADATA:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown agent: {agent_name}",
        )
    repo = SqlAlchemyPromptRepository(db)
    repo.save_prompt(
        agent_name=agent_name,
        system_prompt=payload.system_prompt,
        change_summary=payload.change_summary,
    )
    agents_data = repo.get_all_prompts()
    target = next((a for a in agents_data if a["name"] == agent_name), None)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve updated prompt",
        )
    return PromptSummary(**target)


@router.post("/{agent_name}/reset", response_model=PromptSummary)
def reset_prompt(agent_name: str, db: Annotated[Session, Depends(get_db)]) -> PromptSummary:
    if agent_name not in AGENT_METADATA:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown agent: {agent_name}",
        )
    repo = SqlAlchemyPromptRepository(db)
    repo.reset_to_default(agent_name)
    agents_data = repo.get_all_prompts()
    target = next((a for a in agents_data if a["name"] == agent_name), None)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve reset prompt",
        )
    return PromptSummary(**target)


@router.post("/{agent_name}/test", response_model=TestPromptResponse)
async def test_prompt(
    agent_name: str,
    payload: TestPromptRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TestPromptResponse:
    if agent_name not in AGENT_METADATA or agent_name not in AGENT_CLASSES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown agent: {agent_name}",
        )

    repo = SqlAlchemyPromptRepository(db)
    # If a prompt draft was provided in the request, use it. Otherwise use the active prompt.
    prompt_to_test = (
        payload.system_prompt.strip()
        if payload.system_prompt and payload.system_prompt.strip()
        else repo.get_active_prompt(agent_name)
    )

    llm = build_llm(settings)
    model = settings.generator_model if agent_name == "response" else settings.classifier_model
    agent_cls = AGENT_CLASSES[agent_name]

    # Instantiate the agent with the specified prompt
    agent_instance = agent_cls(
        llm,
        model=model,
        timeout_seconds=settings.agent_timeout_seconds,
        system_prompt=prompt_to_test,
    )

    # Use default sample input if none provided
    test_payload = (
        payload.test_input if payload.test_input else AGENT_METADATA[agent_name]["sample_input"]
    )

    start = time.perf_counter()
    try:
        result = await agent_instance.run(test_payload)
        latency_ms = int((time.perf_counter() - start) * 1000)
        output_dict = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        return TestPromptResponse(
            status="success",
            agent_name=agent_name,
            model=model,
            latency_ms=latency_ms,
            output=output_dict,
            schema_name=agent_instance.output_schema.__name__,
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        fallback_output = agent_instance.fallback(test_payload, exc)
        return TestPromptResponse(
            status="fallback",
            agent_name=agent_name,
            model=model,
            latency_ms=latency_ms,
            output=fallback_output.model_dump(),
            schema_name=agent_instance.output_schema.__name__,
        )
