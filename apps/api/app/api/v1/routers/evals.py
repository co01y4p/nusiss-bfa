import hmac
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import Field

from app.agents.base import StrictAgentModel
from app.agents.classification import ClassificationAgent
from app.agents.extraction import ExtractionAgent
from app.agents.intent import IntentAgent
from app.agents.priority import PriorityAgent
from app.agents.response import ResponseAgent
from app.core.config import Settings, get_settings
from app.llm.factory import build_structured_llm
from app.llm.gateway import StructuredLLM
from app.rag.citation_validator import CitationValidator
from app.rag.retriever import RetrievedChunk
from app.security.prompt_injection import PromptInjectionDetector

router = APIRouter(prefix="/evals", tags=["evaluations"])

EvaluationSuite = Literal[
    "intent",
    "incidents",
    "safety_critical",
    "facility_qa",
    "prompt_injection",
]

MODEL_FALLBACK_REASON_CODES = {
    "CONTROLLED_TEMPLATE",
    "GENERAL_FALLBACK",
    "MANUAL_TRIAGE",
    "RAW_TEXT_FALLBACK",
    "RULE_ENGINE_FALLBACK",
}


class EvaluationModelError(RuntimeError):
    pass


class EvaluationRequest(StrictAgentModel):
    case_id: str = Field(min_length=1, max_length=100)
    suite: EvaluationSuite
    message: str = Field(min_length=1, max_length=8000)
    location: str | None = Field(default=None, max_length=200)
    context: str | None = Field(default=None, max_length=12000)
    chunk_id: str | None = Field(default=None, max_length=100)


class EvaluationResponse(StrictAgentModel):
    case_id: str
    suite: EvaluationSuite
    provider: str
    classifier_model: str
    generator_model: str
    model_invoked: bool
    intent: str | None = None
    category: str | None = None
    priority: str | None = None
    injection_detected: bool = False
    quarantined: bool = False
    response: str | None = None
    citations: list[str] = Field(default_factory=list)
    citations_valid: bool | None = None
    reason_codes: list[str] = Field(default_factory=list)


def require_model_output(reason_codes: list[str]) -> None:
    fallback_codes = MODEL_FALLBACK_REASON_CODES.intersection(reason_codes)
    if fallback_codes:
        raise EvaluationModelError(
            f"The real LLM call did not complete: {', '.join(sorted(fallback_codes))}"
        )


def require_evaluation_access(
    settings: Annotated[Settings, Depends(get_settings)],
    evaluation_key: Annotated[str | None, Header(alias="X-Evaluation-Key")] = None,
) -> Settings:
    allowed_environment = settings.app_env.lower() in {"development", "test", "ci"}
    configured_key = settings.evaluation_key
    if not settings.evaluation_enabled or not allowed_environment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if (
        not configured_key
        or not evaluation_key
        or not hmac.compare_digest(configured_key, evaluation_key)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid evaluation key"
        )
    return settings


async def evaluate_case_once(
    body: EvaluationRequest, *, llm: StructuredLLM, settings: Settings
) -> EvaluationResponse:
    detector = PromptInjectionDetector()
    direct_score = detector.score_input(body.message)
    indirect_score = detector.score_chunk(body.context or "") if body.context else None
    injection_detected = direct_score.is_high_risk or bool(
        indirect_score and indirect_score.is_high_risk
    )
    reasons = [*direct_score.reason_codes]
    if indirect_score:
        reasons.extend(indirect_score.reason_codes)

    if body.suite == "prompt_injection" or injection_detected:
        return EvaluationResponse(
            case_id=body.case_id,
            suite=body.suite,
            provider=settings.llm_provider,
            classifier_model=settings.classifier_model,
            generator_model=settings.generator_model,
            model_invoked=False,
            injection_detected=injection_detected,
            quarantined=injection_detected,
            reason_codes=sorted(set(reasons)),
        )

    classifier_model = settings.classifier_model
    generator_model = settings.generator_model
    timeout = settings.agent_timeout_seconds

    if body.suite == "intent":
        output = await IntentAgent(
            llm,
            model=classifier_model,
            timeout_seconds=timeout,
            tools=None,
        ).run({"text": body.message, "location": body.location})
        require_model_output(output.reason_codes)
        return EvaluationResponse(
            case_id=body.case_id,
            suite=body.suite,
            provider=settings.llm_provider,
            classifier_model=classifier_model,
            generator_model=generator_model,
            model_invoked=True,
            intent=output.intent.value,
            reason_codes=output.reason_codes,
        )

    if body.suite in {"incidents", "safety_critical"}:
        payload = {"text": body.message, "location": body.location}
        extraction = await ExtractionAgent(
            llm, model=classifier_model, timeout_seconds=timeout
        ).run(payload)
        require_model_output(extraction.reason_codes)
        classification = await ClassificationAgent(
            llm, model=classifier_model, timeout_seconds=timeout
        ).run(payload)
        require_model_output(classification.reason_codes)
        priority = await PriorityAgent(llm, model=classifier_model, timeout_seconds=timeout).decide(
            {
                "text": body.message,
                "hazard_codes": [code.value for code in extraction.hazard_codes],
                "category": classification.category.value,
            }
        )
        require_model_output(priority.reason_codes)
        return EvaluationResponse(
            case_id=body.case_id,
            suite=body.suite,
            provider=settings.llm_provider,
            classifier_model=classifier_model,
            generator_model=generator_model,
            model_invoked=True,
            intent="INCIDENT_REPORT",
            category=classification.category.value,
            priority=priority.priority.value,
            reason_codes=sorted(
                set(extraction.reason_codes + classification.reason_codes + priority.reason_codes)
            ),
        )

    if not body.context or not body.chunk_id:
        return EvaluationResponse(
            case_id=body.case_id,
            suite=body.suite,
            provider=settings.llm_provider,
            classifier_model=classifier_model,
            generator_model=generator_model,
            model_invoked=False,
            response="I do not have enough approved facility information to answer that question.",
            citations_valid=True,
            reason_codes=["NO_APPROVED_CONTEXT"],
        )

    chunk = RetrievedChunk(
        chunk_id=body.chunk_id,
        document_id="evaluation-document",
        document_title="Approved Facility Guide",
        heading="Facility Guidance",
        content=body.context,
        score=1.0,
    )
    response = await ResponseAgent(llm, model=generator_model, timeout_seconds=timeout).run(
        {"text": body.message, "retrieval_chunks": [chunk.model_dump(mode="json")]}
    )
    require_model_output(response.reason_codes)
    citation_result = CitationValidator().validate(
        response_text=response.message,
        citations=response.citations,
        retrieved_chunks=[chunk],
    )
    return EvaluationResponse(
        case_id=body.case_id,
        suite=body.suite,
        provider=settings.llm_provider,
        classifier_model=classifier_model,
        generator_model=generator_model,
        model_invoked=True,
        intent="FACILITY_QA",
        response=response.message,
        citations=response.citations,
        citations_valid=citation_result.is_valid and bool(response.citations),
        reason_codes=sorted(set(response.reason_codes + citation_result.reason_codes)),
    )


@router.post("/run", response_model=EvaluationResponse)
async def run_evaluation(
    body: EvaluationRequest,
    settings: Annotated[Settings, Depends(require_evaluation_access)],
) -> EvaluationResponse:
    try:
        llm = build_structured_llm(settings, allow_fake=False)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A real evaluation LLM is not configured",
        ) from exc
    try:
        return await evaluate_case_once(body, llm=llm, settings=settings)
    except EvaluationModelError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
