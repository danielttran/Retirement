"""Add medicare_irmaa column to projection_year.

Revision ID: 0004_medicare_irmaa
Revises: 0003_debt_and_exclusion
Create Date: 2026-06-03 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_medicare_irmaa"
down_revision: str | None = "0003_debt_and_exclusion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projection_year",
        sa.Column("medicare_irmaa", sa.Text(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("projection_year", "medicare_irmaa")
