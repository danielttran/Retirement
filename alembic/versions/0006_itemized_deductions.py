"""Add itemized_deductions column to assumption_set.

Revision ID: 0006_itemized_deductions
Revises: 0005_ordinary_taxable
Create Date: 2026-06-03 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_itemized_deductions"
down_revision: str | None = "0005_ordinary_taxable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assumption_set",
        sa.Column("itemized_deductions", sa.Text(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("assumption_set", "itemized_deductions")
