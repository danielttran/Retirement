"""Add home-sale columns to account.

Revision ID: 0007_home_sale
Revises: 0006_itemized_deductions
Create Date: 2026-06-03 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_home_sale"
down_revision: str | None = "0006_itemized_deductions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("account", sa.Column("sale_year", sa.Integer(), nullable=True))
    op.add_column(
        "account",
        sa.Column("selling_cost_pct", sa.Text(), nullable=False, server_default="0.06"),
    )


def downgrade() -> None:
    op.drop_column("account", "selling_cost_pct")
    op.drop_column("account", "sale_year")
