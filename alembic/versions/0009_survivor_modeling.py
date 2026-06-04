"""Add death_age (person) and survivor_pct (income_stream) for survivor modeling.

Revision ID: 0009_survivor_modeling
Revises: 0008_housing_rate
Create Date: 2026-06-03 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_survivor_modeling"
down_revision: str | None = "0008_housing_rate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("person", sa.Column("death_age", sa.Integer(), nullable=True))
    op.add_column(
        "income_stream",
        sa.Column("survivor_pct", sa.Text(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("income_stream", "survivor_pct")
    op.drop_column("person", "death_age")
