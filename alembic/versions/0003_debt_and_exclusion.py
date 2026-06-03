"""Add debt payment + withdrawal-exclusion columns to account.

Revision ID: 0003_debt_and_exclusion
Revises: 0002_contribution
Create Date: 2026-06-03 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_debt_and_exclusion"
down_revision: str | None = "0002_contribution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "account",
        sa.Column("debt_annual_payment", sa.Text(), nullable=False, server_default="0"),
    )
    op.add_column(
        "account",
        sa.Column(
            "exclude_from_withdrawals",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("account", "exclude_from_withdrawals")
    op.drop_column("account", "debt_annual_payment")
