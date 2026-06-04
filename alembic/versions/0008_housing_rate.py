"""Add housing_appreciation_rate to assumption_set.

Revision ID: 0008_housing_rate
Revises: 0007_home_sale
Create Date: 2026-06-03 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_housing_rate"
down_revision: str | None = "0007_home_sale"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assumption_set",
        sa.Column("housing_appreciation_rate", sa.Text(), nullable=False, server_default="0.04"),
    )


def downgrade() -> None:
    op.drop_column("assumption_set", "housing_appreciation_rate")
