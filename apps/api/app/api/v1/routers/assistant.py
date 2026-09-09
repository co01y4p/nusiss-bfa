from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy.orm import Session

from app.agents.assignment import AssignmentAgent
from app.agents.base import StrictAgentModel
from app.agents.classification import ClassificationAgent
from app.agents.extraction import ExtractionAgent
from app.agents.intent import IntentAgent
from app.agents.priority import PriorityAgent
from app.agents.response import ResponseAgent
from app.agents.review import ReviewAgent
from app.agents.security import SecurityAgent
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.llm.factory import build_structured_llm
from app.llm.gateway import StructuredLLM
from app.rag.citation_validator import CitationValidator
from app.rag.embeddings import EmbeddingProvider, FakeEmbeddings, OpenAICompatibleEmbeddings
from app.rag.retriever import KnowledgeRetriever
from app.repositories.postgres.incidents import (
    SqlAlchemyIncidentRepository,
    SqlAlchemyWorkflowRunRepository,
)
from app.repositories.postgres.knowledge import SqlAlchemyKnowledgeRepository
from app.repositories.postgres.prompts import SqlAlchemyPromptRepository
from app.repositories.postgres.security_events import PostgresSecurityEventRepository
from app.security.authentication import CurrentUser, require_manager
from app.tools import ToolRegistry, register_incident_tools, register_knowledge_tools
from app.workflows.facility_graph import FacilityWorkflow
from app.workflows.state import TraceStep

router = APIRouter(tags=["assistant"])


class AssistantRequest(StrictAgentModel):
    message: str = Field(min_length=1, max_length=8000)
    location: str | None = Field(default=None, max_length=200)
    include_trace: bool = Field(default=False)


class AssistantResponse(StrictAgentModel):
    outcome: str
    message: str
    reference_code: str | None
    trace: list[TraceStep] | None = Field(default=None)


class TraceResponse(StrictAgentModel):
    id: str
    incident_id: str | None
    outcome: str
    final_response: str
    trace: list[dict[str, Any]]
    created_at: datetime


def build_llm(settings: Settings) -> StructuredLLM:
    return build_structured_llm(settings)


def build_embeddings(settings: Settings) -> EmbeddingProvider:
    has_keys = bool(settings.llm_base_url and settings.llm_api_key)
    if settings.llm_provider in {"openai", "openrouter"} and has_keys:
        return OpenAICompatibleEmbeddings(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.embedding_model,
        )
    return FakeEmbeddings(dim=settings.embedding_dim)


def build_tool_registry(
    incident_repo: SqlAlchemyIncidentRepository, retriever: KnowledgeRetriever
) -> ToolRegistry:
    registry = ToolRegistry()
    register_incident_tools(registry, incident_repo)
    register_knowledge_tools(registry, retriever)
    return registry


def build_workflow(db: Session, settings: Settings) -> FacilityWorkflow:

    llm = build_llm(settings)
    embeddings = build_embeddings(settings)
    knowledge_repo = SqlAlchemyKnowledgeRepository(db)
    prompt_repo = SqlAlchemyPromptRepository(db)
    retriever = KnowledgeRetriever(
        repository=knowledge_repo,
        embeddings=embeddings,
        default_top_k=settings.rag_top_k,
        default_similarity_threshold=settings.rag_similarity_threshold,
    )
    citation_validator = CitationValidator()
    incident_repository = SqlAlchemyIncidentRepository(db)
    tools = build_tool_registry(incident_repository, retriever)

    return FacilityWorkflow(
        settings=settings,
        incident_repository=incident_repository,
        workflow_repository=SqlAlchemyWorkflowRunRepository(db),
        security=SecurityAgent(
            llm,
            model=settings.classifier_model,
            timeout_seconds=settings.agent_timeout_seconds,
            system_prompt=prompt_repo.get_active_prompt("security"),
        ),
        intent=IntentAgent(
            llm,
            model=settings.classifier_model,
            timeout_seconds=settings.agent_timeout_seconds,
            tools=tools,
            system_prompt=prompt_repo.get_active_prompt("intent"),
        ),
        extraction=ExtractionAgent(
            llm,
            model=settings.classifier_model,
            timeout_seconds=settings.agent_timeout_seconds,
            system_prompt=prompt_repo.get_active_prompt("extraction"),
        ),
        classification=ClassificationAgent(
            llm,
            model=settings.classifier_model,
            timeout_seconds=settings.agent_timeout_seconds,
            system_prompt=prompt_repo.get_active_prompt("classification"),
        ),
        priority=PriorityAgent(
            llm,
            model=settings.classifier_model,
            timeout_seconds=settings.agent_timeout_seconds,
            system_prompt=prompt_repo.get_active_prompt("priority"),
        ),
        assignment=AssignmentAgent(
            llm,
            model=settings.classifier_model,
            timeout_seconds=settings.agent_timeout_seconds,
            system_prompt=prompt_repo.get_active_prompt("assignment"),
        ),
        response=ResponseAgent(
            llm,
            model=settings.generator_model,
            timeout_seconds=settings.agent_timeout_seconds,
            system_prompt=prompt_repo.get_active_prompt("response"),
        ),
        review=ReviewAgent(
            llm,
            model=settings.classifier_model,
            timeout_seconds=settings.agent_timeout_seconds,
            system_prompt=prompt_repo.get_active_prompt("review"),
        ),
        retriever=retriever,
        citation_validator=citation_validator,
        security_events=PostgresSecurityEventRepository(db),
        tools=tools,
    )


@router.post(
    "/assistant/messages",
    response_model=AssistantResponse,
    response_model_exclude_none=True,
)
async def submit_message(
    body: AssistantRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssistantResponse:
    try:
        state = await build_workflow(db, settings).run(text=body.message, location=body.location)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The assistant is temporarily unavailable",
        ) from exc
    return AssistantResponse(
        outcome=state.outcome,
        message=state.final_response,
        reference_code=state.reference_code,
        trace=state.trace if body.include_trace else None,
    )


@router.get("/incidents/{incident_id}/trace", response_model=TraceResponse)
def incident_trace(
    incident_id: str,
    db: Annotated[Session, Depends(get_db)],
    manager: Annotated[CurrentUser, Depends(require_manager)],
) -> TraceResponse:
    del manager
    result = SqlAlchemyWorkflowRunRepository(db).get_for_incident(incident_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trace not found")
    return TraceResponse.model_validate(result)
