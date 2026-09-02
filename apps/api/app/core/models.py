import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, TypeDecorator, TypeEngine, UserDefinedType

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


json_type = JSON().with_variant(JSONB, "postgresql")
uuid_type = Uuid(as_uuid=False)


class PGVector(UserDefinedType[Any]):
    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim

    def get_col_spec(self, **kw: object) -> str:
        return f"vector({self.dim})"


class VectorType(TypeDecorator[list[float]]):
    """Stores embeddings as vector(dim) in PostgreSQL and JSON in SQLite/fallback."""

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int = 1536, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.dim = dim

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGVector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: list[float] | None, dialect: Dialect) -> object:
        if value is None:
            return None
        if dialect.name == "postgresql":
            if isinstance(value, (list, tuple)):
                return "[" + ",".join(str(float(x)) for x in value) + "]"
            return str(value)
        return value

    def process_result_value(self, value: object, dialect: Dialect) -> list[float] | None:
        if value is None:
            return None
        if isinstance(value, str) and value.startswith("[") and value.endswith("]"):
            raw = value[1:-1].strip()
            return [float(x) for x in raw.split(",") if x.strip()]
        if isinstance(value, list):
            return [float(x) for x in value]
        return None


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


class KnowledgeDocumentModel(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255), index=True)
    source_path: Mapped[str] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    version: Mapped[str] = mapped_column(String(32), default="1.0")
    effective_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    access_scope: Mapped[str] = mapped_column(String(64), default="PUBLIC", index=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    chunks: Mapped[list["KnowledgeChunkModel"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="KnowledgeChunkModel.chunk_index",
    )


class KnowledgeChunkModel(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(
        uuid_type, ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(index=True)
    heading: Mapped[str] = mapped_column(String(255), default="")
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(default=0)
    embedding: Mapped[list[float]] = mapped_column(VectorType(1536))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    document: Mapped[KnowledgeDocumentModel] = relationship(back_populates="chunks")


class SecurityEventModel(Base):
    __tablename__ = "security_events"

    id: Mapped[str] = mapped_column(uuid_type, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="MEDIUM", index=True)
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, object]] = mapped_column(json_type, default=dict)
    reason_codes: Mapped[list[str]] = mapped_column(json_type, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
