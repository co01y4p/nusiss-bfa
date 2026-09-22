"""Add location_embedding column to incidents table.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.models import VectorType

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("incidents", sa.Column("location_embedding", VectorType(1536), nullable=True))


def downgrade() -> None:
    op.drop_column("incidents", "location_embedding")
