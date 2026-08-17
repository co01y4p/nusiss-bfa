import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


json_type = JSON().with_variant(JSONB, "postgresql")
uuid_type = Uuid(as_uuid=False)


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(32), default="MANAGER")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IncidentModel(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    reference_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="RECEIVED")
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(8), nullable=True)
    assigned_team: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    workflow_runs: Mapped[list["WorkflowRunModel"]] = relationship(back_populates="incident")


class WorkflowRunModel(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    incident_id: Mapped[str | None] = mapped_column(
        uuid_type, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    input_text: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(64))
    final_response: Mapped[str] = mapped_column(Text)
    trace: Mapped[list[dict[str, object]]] = mapped_column(json_type, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    incident: Mapped[IncidentModel | None] = relationship(back_populates="workflow_runs")
