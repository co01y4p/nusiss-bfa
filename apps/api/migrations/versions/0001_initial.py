"""Create users, incidents, and workflow runs.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("reference_code", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("priority", sa.String(length=8), nullable=True),
        sa.Column("assigned_team", sa.String(length=64), nullable=True),
        sa.Column("requires_human_review", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incidents_reference_code", "incidents", ["reference_code"], unique=True)
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("incident_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("outcome", sa.String(length=64), nullable=False),
        sa.Column("final_response", sa.Text(), nullable=False),
        sa.Column("trace", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_runs_incident_id", "workflow_runs", ["incident_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_incident_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_index("ix_incidents_reference_code", table_name="incidents")
    op.drop_table("incidents")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
