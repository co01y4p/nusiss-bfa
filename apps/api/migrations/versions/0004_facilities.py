"""Create floors and facilities tables.

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
        "floors",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "facilities",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("floor_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="GENERAL"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["floor_id"], ["floors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_facilities_floor_id", "facilities", ["floor_id"])


def downgrade() -> None:
    op.drop_index("ix_facilities_floor_id", table_name="facilities")
    op.drop_table("facilities")
    op.drop_table("floors")
