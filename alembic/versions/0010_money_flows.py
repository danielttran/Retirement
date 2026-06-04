"""Add money_flow table (manual scheduled transfers).

Revision ID: 0010_money_flows
Revises: 0009_survivor_modeling
Create Date: 2026-06-03 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_money_flows"
down_revision: str | None = "0009_survivor_modeling"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "money_flow",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("scenario_id", sa.String(), sa.ForeignKey("scenario.id"), nullable=False),
        sa.Column("from_account_id", sa.String(), sa.ForeignKey("account.id"), nullable=False),
        sa.Column("to_account_id", sa.String(), sa.ForeignKey("account.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_money_flow_scenario", "money_flow", ["scenario_id"])


def downgrade() -> None:
    op.drop_index("ix_money_flow_scenario", table_name="money_flow")
    op.drop_table("money_flow")
