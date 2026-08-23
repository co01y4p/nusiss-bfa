"""Create knowledge documents and chunks tables with vector support.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        vector_type = sa.Column("embedding", sa.NullType(), nullable=False)
    else:
        vector_type = sa.Column(
            "embedding", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False
        )

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source_path", sa.String(length=500), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False, server_default="1.0"),
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("access_scope", sa.String(length=64), nullable=False, server_default="PUBLIC"),
        sa.Column("is_approved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_documents_content_hash",
        "knowledge_documents",
        ["content_hash"],
        unique=True,
    )
    op.create_index("ix_knowledge_documents_title", "knowledge_documents", ["title"])
    op.create_index(
        "ix_knowledge_documents_access_scope", "knowledge_documents", ["access_scope"]
    )
    op.create_index("ix_knowledge_documents_is_approved", "knowledge_documents", ["is_approved"])

    if is_postgres:
        op.execute(
            """
            CREATE TABLE knowledge_chunks (
                id UUID PRIMARY KEY,
                document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                heading VARCHAR(255) NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                token_count INTEGER NOT NULL DEFAULT 0,
                embedding vector(1536) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL
            );
            """
        )
    else:
        op.create_table(
            "knowledge_chunks",
            sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
            sa.Column("document_id", sa.Uuid(as_uuid=False), nullable=False),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("heading", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
            vector_type,
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    op.create_index(
        "ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"], unique=False
    )
    op.create_index(
        "ix_knowledge_chunks_chunk_index", "knowledge_chunks", ["chunk_index"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_chunk_index", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_document_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index("ix_knowledge_documents_is_approved", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_access_scope", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_title", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_content_hash", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
