import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.models import IncidentModel, WorkflowRunModel
from app.domain.incidents.models import Incident, IncidentStatus


def _to_domain(row: IncidentModel) -> Incident:
    return Incident(
        id=row.id,
        reference_code=row.reference_code,
        description=row.description,
        location=row.location,
        status=IncidentStatus(row.status),
        category=row.category,
        priority=row.priority,
        assigned_team=row.assigned_team,
        requires_human_review=row.requires_human_review,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _reference_code() -> str:
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "BFA-" + "".join(secrets.choice(alphabet) for _ in range(10))


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SqlAlchemyIncidentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, *, description: str, location: str) -> Incident:
        for _ in range(4):
            row = IncidentModel(
                reference_code=_reference_code(),
                description=description.strip(),
                location=location.strip(),
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
        return _to_domain(row) if row else None

    def get_by_reference(self, reference_code: str) -> Incident | None:
        row = self.session.scalar(
            select(IncidentModel).where(
                IncidentModel.reference_code == reference_code.strip().upper()
            )
        )
        return _to_domain(row) if row else None

    def list_recent(self, *, limit: int = 200, offset: int = 0) -> list[Incident]:
        rows = self.session.scalars(
            select(IncidentModel)
            .order_by(IncidentModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return [_to_domain(row) for row in rows]

    def find_similar(
        self,
        *,
        location: str,
        since: datetime,
        exclude_id: str | None = None,
        limit: int = 5,
    ) -> list[Incident]:
        stmt = (
            select(IncidentModel)
            .where(IncidentModel.location.ilike(f"%{_escape_like(location)}%", escape="\\"))
            .where(IncidentModel.created_at >= since)
            .order_by(IncidentModel.created_at.desc())
            .limit(limit)
        )
        if exclude_id is not None:
            stmt = stmt.where(IncidentModel.id != exclude_id)
        rows = self.session.scalars(stmt).all()
        return [_to_domain(row) for row in rows]

    def update_status(self, incident_id: str, status: str) -> Incident | None:
        row = self.session.get(IncidentModel, incident_id)
        if row is None:
            return None
        row.status = status
        row.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(row)
        return _to_domain(row)

    def update_triage(
        self,
        incident_id: str,
        *,
        location: str,
        category: str,
        priority: str,
        assigned_team: str,
        requires_human_review: bool,
    ) -> Incident | None:
        row = self.session.get(IncidentModel, incident_id)
        if row is None:
            return None
        row.location = location
        row.category = category
        row.priority = priority
        row.assigned_team = assigned_team
        row.requires_human_review = requires_human_review
        row.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(row)
        return _to_domain(row)


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
