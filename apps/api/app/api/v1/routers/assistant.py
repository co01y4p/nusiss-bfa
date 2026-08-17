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
from app.repositories.postgres.incidents import (
    SqlAlchemyIncidentRepository,
    SqlAlchemyWorkflowRunRepository,
)
from app.security.authentication import CurrentUser, require_manager
from app.workflows.facility_graph import FacilityWorkflow

router = APIRouter(tags=["assistant"])


class AssistantRequest(StrictAgentModel):
    message: str = Field(min_length=1, max_length=8000)
    location: str | None = Field(default=None, max_length=200)


class AssistantResponse(StrictAgentModel):
    outcome: str
    message: str
    reference_code: str | None


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
    if settings.llm_provider in {"openai", "openrouter"}:
        if not settings.llm_base_url or not settings.llm_api_key:
            raise RuntimeError("External LLM provider is not configured")
        return OpenAICompatibleStructuredLLM(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
        )
    raise RuntimeError(f"Unsupported LLM provider: {settings.llm_provider}")


def build_workflow(db: Session, settings: Settings) -> FacilityWorkflow:
    llm = build_llm(settings)
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
    )


@router.post("/assistant/messages", response_model=AssistantResponse)
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
