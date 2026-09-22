import math
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.models import IncidentModel, WorkflowRunModel
from app.domain.incidents.models import Incident, IncidentStatus


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _to_domain(row: IncidentModel, *, intent: str | None = None) -> Incident:
    return Incident(
        id=row.id,
        reference_code=row.reference_code,
        description=row.description,
        location=row.location,
        status=IncidentStatus(row.status),
        category=row.category,
        priority=row.priority,
        assigned_team=row.assigned_team,
        intent=intent,
        requires_human_review=row.requires_human_review,
        override_reason=row.override_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _extract_intent(trace: list[dict[str, object]] | None) -> str | None:
    for step in trace or []:
        if step.get("node") in ("intent", "intent_finalize"):
            output = step.get("output")
            value = output.get("intent") if isinstance(output, dict) else None
            if isinstance(value, str):
                return value
    return None


def _latest_intents(session: Session, incident_ids: list[str]) -> dict[str, str | None]:
    """Most recent workflow run's intent per incident, read from the
    already-persisted trace JSON (no dedicated `intent` column exists)."""
    if not incident_ids:
        return {}
    rows = session.scalars(
        select(WorkflowRunModel)
        .where(WorkflowRunModel.incident_id.in_(incident_ids))
        .order_by(WorkflowRunModel.created_at.desc())
    ).all()
    result: dict[str, str | None] = {}
    for row in rows:
        incident_id = row.incident_id
        if incident_id is None or incident_id in result:
            continue
        result[incident_id] = _extract_intent(row.trace)
    return result


def _reference_code() -> str:
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "BFA-" + "".join(secrets.choice(alphabet) for _ in range(10))


class SqlAlchemyIncidentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self, *, description: str, location: str, location_embedding: list[float] | None = None
    ) -> Incident:
        for _ in range(4):
            row = IncidentModel(
                reference_code=_reference_code(),
                description=description.strip(),
                location=location.strip(),
                location_embedding=location_embedding,
                status=IncidentStatus.RECEIVED.value,
            )
            self.session.add(row)
            try:
                self.session.commit()
                self.session.refresh(row)
                return _to_domain(row)
            except IntegrityError:
                self.session.rollback()
        raise RuntimeError("Unable to allocate a unique incident reference code")

    def get_by_id(self, incident_id: str) -> Incident | None:
        row = self.session.get(IncidentModel, incident_id)
        if row is None:
            return None
        return _to_domain(row, intent=_latest_intents(self.session, [row.id]).get(row.id))

    def get_by_reference(self, reference_code: str) -> Incident | None:
        row = self.session.scalar(
            select(IncidentModel).where(
                IncidentModel.reference_code == reference_code.strip().upper()
            )
        )
        if row is None:
            return None
        return _to_domain(row, intent=_latest_intents(self.session, [row.id]).get(row.id))

    def list_recent(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
        requires_human_review: bool | None = None,
        status: str | None = None,
        priority: str | None = None,
    ) -> list[Incident]:
        stmt = select(IncidentModel)
        if requires_human_review is not None:
            stmt = stmt.where(IncidentModel.requires_human_review == requires_human_review)
        if status is not None:
            stmt = stmt.where(IncidentModel.status == status)
        if priority is not None:
            stmt = stmt.where(IncidentModel.priority == priority)
        stmt = stmt.order_by(IncidentModel.created_at.desc()).limit(limit).offset(offset)
        rows = self.session.scalars(stmt).all()
        intents = _latest_intents(self.session, [row.id for row in rows])
        return [_to_domain(row, intent=intents.get(row.id)) for row in rows]

    def find_similar(
        self,
        *,
        location_embedding: list[float],
        since: datetime,
        exclude_id: str | None = None,
        limit: int = 5,
        similarity_threshold: float = 0.75,
    ) -> list[Incident]:
        stmt = (
            select(IncidentModel)
            .where(IncidentModel.location_embedding.is_not(None))
            .where(IncidentModel.created_at >= since)
            .order_by(IncidentModel.created_at.desc())
        )
        if exclude_id is not None:
            stmt = stmt.where(IncidentModel.id != exclude_id)
        candidates = self.session.scalars(stmt).all()

        scored = [
            (row, _cosine_similarity(location_embedding, row.location_embedding))
            for row in candidates
            if row.location_embedding
        ]
        scored = [item for item in scored if item[1] >= similarity_threshold]
        scored.sort(key=lambda item: item[1], reverse=True)
        return [_to_domain(row) for row, _ in scored[:limit]]

    def update_status(self, incident_id: str, status: str, *, reason: str) -> Incident | None:
        row = self.session.get(IncidentModel, incident_id)
        if row is None:
            return None
        row.status = status
        row.override_reason = reason
        row.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(row)
        return _to_domain(row, intent=_latest_intents(self.session, [row.id]).get(row.id))

    def update_triage(
        self,
        incident_id: str,
        *,
        location: str,
        category: str,
        priority: str,
        assigned_team: str,
        requires_human_review: bool,
        reason: str | None = None,
    ) -> Incident | None:
        row = self.session.get(IncidentModel, incident_id)
        if row is None:
            return None
        row.location = location
        row.category = category
        row.priority = priority
        row.assigned_team = assigned_team
        row.requires_human_review = requires_human_review
        if reason:
            row.override_reason = reason
        row.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(row)
        return _to_domain(row, intent=_latest_intents(self.session, [row.id]).get(row.id))

    def mark_requires_human_review(self, incident_id: str) -> None:
        row = self.session.get(IncidentModel, incident_id)
        if row is not None:
            row.requires_human_review = True
            row.updated_at = datetime.now(UTC)
            self.session.commit()


class SqlAlchemyWorkflowRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(
        self,
        *,
        incident_id: str | None,
        input_text: str,
        outcome: str,
        final_response: str,
        trace: list[dict[str, object]],
    ) -> str:
        row = WorkflowRunModel(
            incident_id=incident_id,
            input_text=input_text,
            outcome=outcome,
            final_response=final_response,
            trace=trace,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row.id

    def get_for_incident(self, incident_id: str) -> dict[str, object] | None:
        row = self.session.scalar(
            select(WorkflowRunModel)
            .where(WorkflowRunModel.incident_id == incident_id)
            .order_by(WorkflowRunModel.created_at.desc())
        )
        if row is None:
            return None
        return {
            "id": row.id,
            "incident_id": row.incident_id,
            "outcome": row.outcome,
            "final_response": row.final_response,
            "trace": row.trace,
            "created_at": row.created_at,
        }
