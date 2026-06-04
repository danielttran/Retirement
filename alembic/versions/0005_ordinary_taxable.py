"""Add ordinary_taxable_income column to projection_year.

Revision ID: 0005_ordinary_taxable
Revises: 0004_medicare_irmaa
Create Date: 2026-06-03 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_ordinary_taxable"
down_revision: str | None = "0004_medicare_irmaa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projection_year",
        sa.Column("ordinary_taxable_income", sa.Text(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("projection_year", "ordinary_taxable_income")
