import asyncio
from typing import Any, Protocol

from pydantic import BaseModel

from app.agents.assignment import AssignmentAgent
from app.agents.classification import ClassificationAgent
from app.agents.extraction import ExtractionAgent
from app.agents.intent import Intent, IntentAgent
from app.agents.priority import PriorityAgent
from app.agents.response import ResponseAgent
from app.agents.review import ReviewAgent
from app.agents.security import SecurityAgent
from app.core.config import Settings
from app.domain.incidents.models import IncidentCreate
from app.rag.citation_validator import CitationValidator
from app.rag.retriever import KnowledgeRetriever
from app.repositories.interfaces.incidents import IncidentRepository, WorkflowRunRepository
from app.services.incident_service import IncidentService
from app.workflows.state import WorkflowState


class WorkflowLimitError(RuntimeError):
    pass


class WorkflowEngine(Protocol):
    async def run(self, *, text: str, location: str | None = None) -> WorkflowState: ...


class FacilityWorkflow:
    def __init__(
        self,
        *,
        settings: Settings,
        incident_repository: IncidentRepository,
        workflow_repository: WorkflowRunRepository,
        security: SecurityAgent,
        intent: IntentAgent,
        extraction: ExtractionAgent,
        classification: ClassificationAgent,
        priority: PriorityAgent,
        assignment: AssignmentAgent,
        response: ResponseAgent,
        review: ReviewAgent,
        retriever: KnowledgeRetriever | None = None,
        citation_validator: CitationValidator | None = None,
    ) -> None:
        self.settings = settings
        self.incidents = incident_repository
        self.runs = workflow_repository
        self.security = security
        self.intent = intent
        self.extraction = extraction
        self.classification = classification
        self.priority = priority
        self.assignment = assignment
        self.response = response
        self.review = review
        self.retriever = retriever
        self.citation_validator = citation_validator or CitationValidator()

    def _check_bounds(self, state: WorkflowState, *, model_call: bool = False) -> None:
        if state.step_count >= self.settings.max_agent_steps:
            raise WorkflowLimitError("Maximum workflow steps exceeded")
        if model_call:
            if state.model_calls >= self.settings.max_model_calls:
                raise WorkflowLimitError("Maximum model calls exceeded")
            state.model_calls += 1

    def _record(
        self,
        state: WorkflowState,
        node: str,
        output: dict[str, Any],
        reason_codes: list[str],
    ) -> None:
        self._check_bounds(state)
        state.record(node, output, reason_codes)

    def _record_model_output(self, state: WorkflowState, node: str, output: BaseModel) -> None:
        data = output.model_dump(mode="json")
        reasons = data.get("reason_codes", [])
        self._record(state, node, data, reasons if isinstance(reasons, list) else [])

    async def run(self, *, text: str, location: str | None = None) -> WorkflowState:
        normalized = text.strip()
        if not normalized:
            raise ValueError("Message must not be empty")
        if len(normalized) > self.settings.max_input_chars:
            raise ValueError("Message exceeds the configured input limit")
        state = WorkflowState(input_text=normalized, supplied_location=location)
        try:
            async with asyncio.timeout(self.settings.workflow_timeout_seconds):
                await self._execute(state)
        except (TimeoutError, WorkflowLimitError) as exc:
            state.outcome = "HUMAN_REVIEW"
            state.final_response = (
                "The automated workflow stopped safely. A manager will review it."
            )
            if state.step_count < self.settings.max_agent_steps:
                state.record("human_review", {"error": str(exc)}, ["WORKFLOW_BOUND_REACHED"])
        self._save_run(state)
        return state

    async def _execute(self, state: WorkflowState) -> None:
        payload: dict[str, Any] = {
            "text": state.input_text,
            "location": state.supplied_location,
        }

        self._check_bounds(state, model_call=True)
        security = await self.security.run(payload)
        self._record_model_output(state, "security", security)
        if security.risk_score >= 0.8:
            state.outcome = "QUARANTINED"
            state.final_response = "This request was quarantined for manager review."
            self._record(
                state,
                "quarantine",
                {"risk_labels": security.risk_labels},
                ["HIGH_RISK_INPUT"],
            )
            return

        self._check_bounds(state, model_call=True)
        intent = await self.intent.run(payload)
        self._record_model_output(state, "intent", intent)

        if intent.intent == Intent.INCIDENT_REPORT:
            await self._incident_path(state, payload)
        elif intent.intent == Intent.FACILITY_QA:
            await self._faq_path(state, payload)
        else:
            state.outcome = "HUMAN_REVIEW"
            state.final_response = "A facility manager will review this request."
            self._record(
                state,
                "human_review",
                {"intent": intent.intent.value},
                ["UNSUPPORTED_INTENT", "MANUAL_TRIAGE"],
            )

    async def _incident_path(self, state: WorkflowState, payload: dict[str, Any]) -> None:
        location = state.supplied_location.strip() if state.supplied_location else "Unspecified"
        incident = IncidentService(self.incidents).create(
            IncidentCreate(description=state.input_text, location=location)
        )
        state.incident_id = incident.id
        state.reference_code = incident.reference_code
        self._record(
            state,
            "persist_incident",
            {"incident_id": incident.id, "reference_code": incident.reference_code},
            ["SAVE_BEFORE_AI"],
        )

        self._check_bounds(state, model_call=True)
        extraction = await self.extraction.run(payload)
        self._record_model_output(state, "extract", extraction)

        classify_payload = {"text": state.input_text, "summary": extraction.summary}
        self._check_bounds(state, model_call=True)
        classification = await self.classification.run(classify_payload)
        self._record_model_output(state, "classify", classification)

        priority_payload = {
            "text": state.input_text,
            "hazard_codes": [code.value for code in extraction.hazard_codes],
            "category": classification.category.value,
        }
        self._check_bounds(state, model_call=True)
        priority = await self.priority.decide(priority_payload)
        self._record_model_output(state, "priority", priority)
        if priority.priority.value == "P1":
            self._record(
                state,
                "notify_critical",
                {"notification": "MANAGER_QUEUE"},
                ["CRITICAL_NOTIFICATION_RECORDED"],
            )

        assignment_payload = {
            "category": classification.category.value,
            "priority": priority.priority.value,
        }
        self._check_bounds(state, model_call=True)
        assignment = await self.assignment.run(assignment_payload)
        self._record_model_output(state, "assign", assignment)

        self.incidents.update_triage(
            incident.id,
            location=extraction.location,
            category=classification.category.value,
            priority=priority.priority.value,
            assigned_team=assignment.team.value,
            requires_human_review=priority.requires_human_review or bool(extraction.missing_fields),
        )

        retrieved_chunks = []
        if self.retriever:
            retrieved_chunks = await self.retriever.search(
                state.input_text, top_k=3, access_scope="PUBLIC", must_be_approved=True
            )

        chunks_data = [c.model_dump(mode="json") for c in retrieved_chunks]
        self._record(
            state,
            "incident_retrieval",
            {"chunks": chunks_data, "count": len(chunks_data)},
            ["APPROVED_CONTEXT_RETRIEVED"] if chunks_data else ["NO_APPROVED_CONTEXT"],
        )
        response_payload: dict[str, Any] = {
            "reference_code": incident.reference_code,
            "priority": priority.priority.value,
            "assigned_team": assignment.team.value,
            "retrieval_chunks": chunks_data,
        }
        self._check_bounds(state, model_call=True)
        response = await self.response.run(response_payload)
        self._record_model_output(state, "incident_response", response)
        await self._review_and_finalize(
            state, response.message, response.citations, retrieved_chunks=retrieved_chunks
        )

    async def _faq_path(self, state: WorkflowState, payload: dict[str, Any]) -> None:
        retrieved_chunks = []
        if self.retriever:
            retrieved_chunks = await self.retriever.search(
                state.input_text,
                top_k=self.settings.rag_top_k,
                access_scope="PUBLIC",
                must_be_approved=True,
            )

        chunks_data = [c.model_dump(mode="json") for c in retrieved_chunks]
        self._record(
            state,
            "faq_retrieval",
            {"query": state.input_text, "chunks": chunks_data, "count": len(chunks_data)},
            ["APPROVED_CONTEXT_RETRIEVED"] if chunks_data else ["NO_APPROVED_CONTEXT"],
        )

        if not retrieved_chunks:
            # Fallback when no approved knowledge exists for the query
            state.outcome = "FINALIZED"
            state.final_response = (
                "I do not have enough approved facility information to answer that question."
            )
            self._record(
                state,
                "finalize",
                {"message": state.final_response},
                ["NO_APPROVED_CONTEXT_FALLBACK"],
            )
            return

        self._check_bounds(state, model_call=True)
        response = await self.response.run({**payload, "retrieval_chunks": chunks_data})
        self._record_model_output(state, "faq_response", response)

        # Citation validation
        val_result = self.citation_validator.validate(
            response_text=response.message,
            citations=response.citations,
            retrieved_chunks=retrieved_chunks,
        )
        self._record(
            state,
            "citation_validation",
            {
                "is_valid": val_result.is_valid,
                "valid_citations": val_result.valid_citations,
                "invalid_citations": val_result.invalid_citations,
                "issues": val_result.issues,
            },
            val_result.reason_codes,
        )

        await self._review_and_finalize(
            state,
            response.message,
            response.citations,
            retrieved_chunks=retrieved_chunks,
            validator_issues=val_result.issues if not val_result.is_valid else None,
        )

    async def _review_and_finalize(
        self,
        state: WorkflowState,
        message: str,
        citations: list[str],
        retrieved_chunks: list[Any] | None = None,
        validator_issues: list[str] | None = None,
    ) -> None:
        del retrieved_chunks
        self._check_bounds(state, model_call=True)
        review = await self.review.run(
            {
                "response_type": (
                    "INCIDENT_ACKNOWLEDGEMENT" if state.incident_id else "FACILITY_ANSWER"
                ),
                "message": message,
                "citations": citations,
                "reference_code": state.reference_code,
                "validator_issues": validator_issues or [],
            }
        )
        self._record_model_output(state, "review", review)
        if review.approved and not validator_issues:
            state.outcome = "FINALIZED"
            state.final_response = message
            self._record(state, "finalize", {"message": message}, ["REVIEW_APPROVED"])
        else:
            issues = (validator_issues or []) + review.issues
            state.outcome = "HUMAN_REVIEW"
            state.final_response = "A facility manager will review this request."
            self._record(
                state,
                "human_review",
                {"issues": issues},
                review.reason_codes or ["CITATION_OR_SAFETY_REJECTED"],
            )

    def _save_run(self, state: WorkflowState) -> None:
        self.runs.save(
            incident_id=state.incident_id,
            input_text=state.input_text,
            outcome=state.outcome,
            final_response=state.final_response,
            trace=[step.model_dump(mode="json") for step in state.trace],
        )
