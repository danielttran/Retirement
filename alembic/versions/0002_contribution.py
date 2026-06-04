"""Add contribution table (accumulation-phase savings + employer match).

Revision ID: 0002_contribution
Revises: 0001_initial
Create Date: 2026-06-03 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_contribution"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contribution",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("scenario_id", sa.String(), sa.ForeignKey("scenario.id"), nullable=False),
        sa.Column("account_id", sa.String(), sa.ForeignKey("account.id"), nullable=False),
        sa.Column("annual_amount", sa.Text(), nullable=False),
        sa.Column("start_year", sa.Integer(), nullable=False),
        sa.Column("end_year", sa.Integer(), nullable=True),
        sa.Column("inflation_kind", sa.String(), nullable=False, server_default="cpi"),
        sa.Column("custom_inflation_rate", sa.Text(), nullable=True),
        sa.Column("employer_match_amount", sa.Text(), nullable=False, server_default="0"),
    )
    op.create_index("ix_contribution_scenario", "contribution", ["scenario_id"])


def downgrade() -> None:
    op.drop_index("ix_contribution_scenario", table_name="contribution")
    op.drop_table("contribution")
