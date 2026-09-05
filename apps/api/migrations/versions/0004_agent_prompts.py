"""Create agent_prompts table.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_prompts",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False, server_default="custom"),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("change_summary", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_prompts_agent_name", "agent_prompts", ["agent_name"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_agent_prompts_agent_name", table_name="agent_prompts")
    op.drop_table("agent_prompts")
