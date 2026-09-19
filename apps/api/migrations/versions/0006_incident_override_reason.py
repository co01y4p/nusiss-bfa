"""Add override_reason column to incidents table.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("incidents", sa.Column("override_reason", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("incidents", "override_reason")
