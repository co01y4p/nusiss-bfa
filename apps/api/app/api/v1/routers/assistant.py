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
from app.llm.fake import FakeStructuredLLM
from app.llm.gateway import StructuredLLM
from app.llm.providers.openai_compatible import OpenAICompatibleStructuredLLM
from app.rag.citation_validator import CitationValidator
from app.rag.embeddings import EmbeddingProvider, FakeEmbeddings, OpenAICompatibleEmbeddings
from app.rag.retriever import KnowledgeRetriever
from app.repositories.postgres.incidents import (
    SqlAlchemyIncidentRepository,
    SqlAlchemyWorkflowRunRepository,
)
from app.repositories.postgres.knowledge import SqlAlchemyKnowledgeRepository
from app.repositories.postgres.security_events import PostgresSecurityEventRepository
from app.security.authentication import CurrentUser, require_manager
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
    if settings.llm_provider == "fake":
        return FakeStructuredLLM()
    if settings.llm_provider in {"openai", "openrouter", "gemini"}:
        base_url = settings.llm_base_url
        if settings.llm_provider == "gemini" and not base_url:
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
        if not base_url or not settings.llm_api_key:
            raise RuntimeError("External LLM provider is not configured")
        return OpenAICompatibleStructuredLLM(
            base_url=base_url,
            api_key=settings.llm_api_key,
            api_style="responses" if settings.llm_provider == "openai" else "chat_completions",
            reasoning_effort=settings.llm_reasoning_effort,
            max_output_tokens=settings.llm_max_output_tokens,
        )
    raise RuntimeError(f"Unsupported LLM provider: {settings.llm_provider}")


def build_embeddings(settings: Settings) -> EmbeddingProvider:
    has_keys = bool(settings.llm_base_url and settings.llm_api_key)
    if settings.llm_provider in {"openai", "openrouter"} and has_keys:
        return OpenAICompatibleEmbeddings(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.embedding_model,
        )
    return FakeEmbeddings(dim=settings.embedding_dim)


def build_workflow(db: Session, settings: Settings) -> FacilityWorkflow:
    llm = build_llm(settings)
    embeddings = build_embeddings(settings)
    knowledge_repo = SqlAlchemyKnowledgeRepository(db)
    retriever = KnowledgeRetriever(
        repository=knowledge_repo,
        embeddings=embeddings,
        default_top_k=settings.rag_top_k,
        default_similarity_threshold=settings.rag_similarity_threshold,
    )
    citation_validator = CitationValidator()

    return FacilityWorkflow(
        settings=settings,
        incident_repository=SqlAlchemyIncidentRepository(db),
        workflow_repository=SqlAlchemyWorkflowRunRepository(db),
        security=SecurityAgent(
            llm,
            model=settings.classifier_model,
            timeout_seconds=settings.agent_timeout_seconds,
        ),
        intent=IntentAgent(
            llm,
            model=settings.classifier_model,
            timeout_seconds=settings.agent_timeout_seconds,
        ),
        extraction=ExtractionAgent(
            llm,
            model=settings.classifier_model,
            timeout_seconds=settings.agent_timeout_seconds,
        ),
        classification=ClassificationAgent(
            llm,
            model=settings.classifier_model,
            timeout_seconds=settings.agent_timeout_seconds,
        ),
        priority=PriorityAgent(
            llm,
            model=settings.classifier_model,
            timeout_seconds=settings.agent_timeout_seconds,
        ),
        assignment=AssignmentAgent(
            llm,
            model=settings.classifier_model,
            timeout_seconds=settings.agent_timeout_seconds,
        ),
        response=ResponseAgent(
            llm, model=settings.generator_model, timeout_seconds=settings.agent_timeout_seconds
        ),
        review=ReviewAgent(
            llm,
            model=settings.classifier_model,
            timeout_seconds=settings.agent_timeout_seconds,
        ),
        retriever=retriever,
        citation_validator=citation_validator,
        security_events=PostgresSecurityEventRepository(db),
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
