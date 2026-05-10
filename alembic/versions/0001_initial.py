"""Initial domain schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-09 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def money(nullable: bool = False) -> sa.Column:
    return sa.Column(sa.Text(), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "household",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("filing_status", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False, server_default="MA"),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_table(
        "person",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("household_id", sa.String(), sa.ForeignKey("household.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("dob", sa.String(), nullable=False),
        sa.Column("retirement_date", sa.String(), nullable=True),
        sa.Column("life_expectancy_age", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "scenario",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("household_id", sa.String(), sa.ForeignKey("household.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("parent_scenario_id", sa.String(), sa.ForeignKey("scenario.id")),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_table(
        "account",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("household_id", sa.String(), sa.ForeignKey("household.id"), nullable=False),
        sa.Column("owner_person_id", sa.String(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("account_type", sa.String(), nullable=False),
        sa.Column("current_balance", sa.Text(), nullable=False),
        sa.Column("expected_return", sa.Text(), nullable=False),
        sa.Column("return_stddev", sa.Text(), nullable=True),
        sa.Column("cost_basis_pct", sa.Text(), nullable=True),
        sa.Column("roth_first_contribution_year", sa.Integer(), nullable=True),
        sa.Column("is_governmental_457b", sa.Boolean(), nullable=False),
        sa.Column("has_rollover_basis_from_penalty_account", sa.Boolean(), nullable=False),
        sa.Column("rollover_basis_pct", sa.Text(), nullable=True),
        sa.Column("hsa_qualified_medical_expense_pct", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index("ix_account_household", "account", ["household_id"])
    op.create_table(
        "roth_basis",
        sa.Column("account_id", sa.String(), sa.ForeignKey("account.id"), primary_key=True),
        sa.Column("contributions_basis", sa.Text(), nullable=False),
        sa.Column("conversions_basis", sa.Text(), nullable=False),
        sa.Column("earnings_balance", sa.Text(), nullable=False),
    )
    op.create_table(
        "roth_conversion_lot",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("account_id", sa.String(), sa.ForeignKey("account.id"), nullable=False),
        sa.Column("conversion_year", sa.Integer(), nullable=False),
        sa.Column("converted_amount", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_roth_conv_lot_account", "roth_conversion_lot", ["account_id"])
    op.create_table(
        "income_stream",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("household_id", sa.String(), sa.ForeignKey("household.id"), nullable=False),
        sa.Column("person_id", sa.String(), sa.ForeignKey("person.id"), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("annual_amount", sa.Text(), nullable=False),
        sa.Column("start_year", sa.Integer(), nullable=False),
        sa.Column("end_year", sa.Integer(), nullable=True),
        sa.Column("inflation_kind", sa.String(), nullable=False),
        sa.Column("custom_inflation_rate", sa.Text(), nullable=True),
        sa.Column("is_taxable_federal", sa.Boolean(), nullable=False),
        sa.Column("is_taxable_state", sa.Boolean(), nullable=False),
        sa.Column("claiming_age", sa.Integer(), nullable=True),
    )
    op.create_table(
        "expense_stream",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("household_id", sa.String(), sa.ForeignKey("household.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("annual_amount", sa.Text(), nullable=False),
        sa.Column("start_year", sa.Integer(), nullable=False),
        sa.Column("end_year", sa.Integer(), nullable=True),
        sa.Column("inflation_kind", sa.String(), nullable=False),
        sa.Column("custom_inflation_rate", sa.Text(), nullable=True),
    )
    op.create_table(
        "assumption_set",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("scenario_id", sa.String(), sa.ForeignKey("scenario.id"), unique=True),
        sa.Column("cpi_rate", sa.Text(), nullable=False),
        sa.Column("healthcare_inflation_rate", sa.Text(), nullable=False),
        sa.Column("ss_cola_rate", sa.Text(), nullable=False),
        sa.Column("pension_cola_rate", sa.Text(), nullable=False),
        sa.Column("bracket_indexing_rate", sa.Text(), nullable=False),
        sa.Column("cash_reserve_target_months", sa.Integer(), nullable=False),
        sa.Column("irs_data_version", sa.String(), nullable=False),
        sa.Column("engine_version", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("tax_iteration_max", sa.Integer(), nullable=False),
        sa.Column("tax_iteration_tolerance", sa.Text(), nullable=False),
    )
    op.create_table(
        "withdrawal_strategy",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("scenario_id", sa.String(), sa.ForeignKey("scenario.id"), unique=True),
        sa.Column("order_json", sa.Text(), nullable=False),
        sa.Column("surplus_target", sa.String(), nullable=False),
    )
    op.create_table(
        "sepp_plan",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("scenario_id", sa.String(), sa.ForeignKey("scenario.id"), nullable=False),
        sa.Column("account_id", sa.String(), sa.ForeignKey("account.id"), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("valuation_date", sa.String(), nullable=False),
        sa.Column("first_payment_date", sa.String(), nullable=False),
        sa.Column("required_end_date", sa.String(), nullable=False),
        sa.Column("age_at_first_payment", sa.Text(), nullable=False),
        sa.Column("account_balance_at_valuation", sa.Text(), nullable=False),
        sa.Column("afr_prior_month", sa.Text(), nullable=True),
        sa.Column("afr_two_months_prior", sa.Text(), nullable=True),
        sa.Column("afr_month_used", sa.String(), nullable=True),
        sa.Column("selected_interest_rate", sa.Text(), nullable=True),
        sa.Column("max_allowed_interest_rate", sa.Text(), nullable=True),
        sa.Column("initial_life_expectancy_factor", sa.Text(), nullable=True),
        sa.Column("initial_annual_payment_locked", sa.Text(), nullable=True),
        sa.Column("irs_notice_version", sa.String(), nullable=False),
        sa.Column("mortality_table_version", sa.String(), nullable=True),
        sa.Column("beneficiary_dob_snapshot", sa.String(), nullable=True),
        sa.Column("calculation_log_json", sa.Text(), nullable=True),
        sa.Column("has_switched_to_rmd", sa.Boolean(), nullable=False),
        sa.Column("switched_to_rmd_year", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ux_sepp_active_per_account",
        "sepp_plan",
        ["account_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('planned','active')"),
    )
    op.create_table(
        "roth_conversion_plan",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("scenario_id", sa.String(), sa.ForeignKey("scenario.id"), nullable=False),
        sa.Column("source_account_id", sa.String(), sa.ForeignKey("account.id"), nullable=False),
        sa.Column(
            "destination_account_id", sa.String(), sa.ForeignKey("account.id"), nullable=False
        ),
        sa.Column(
            "tax_payment_source_account_id",
            sa.String(),
            sa.ForeignKey("account.id"),
            nullable=True,
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_roth_conv_plan_scenario", "roth_conversion_plan", ["scenario_id", "year"]
    )
    op.create_table(
        "projection_run_metadata",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("scenario_id", sa.String(), sa.ForeignKey("scenario.id"), nullable=False),
        sa.Column("run_at", sa.String(), nullable=False),
        sa.Column("engine_version", sa.String(), nullable=False),
        sa.Column("irs_data_version", sa.String(), nullable=False),
        sa.Column("assumption_snapshot_json", sa.Text(), nullable=False),
        sa.Column("convergence_log_json", sa.Text(), nullable=True),
    )
    op.create_table(
        "projection_year",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("scenario_id", sa.String(), sa.ForeignKey("scenario.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("age_primary", sa.Integer(), nullable=False),
        sa.Column("age_spouse", sa.Integer(), nullable=True),
        sa.Column("gross_income", sa.Text(), nullable=False),
        sa.Column("required_distributions", sa.Text(), nullable=False),
        sa.Column("flexible_withdrawals", sa.Text(), nullable=False),
        sa.Column("roth_conversions", sa.Text(), nullable=False),
        sa.Column("expenses", sa.Text(), nullable=False),
        sa.Column("federal_tax", sa.Text(), nullable=False),
        sa.Column("state_tax", sa.Text(), nullable=False),
        sa.Column("early_withdrawal_penalty", sa.Text(), nullable=False),
        sa.Column("magi", sa.Text(), nullable=False),
        sa.Column("provisional_income", sa.Text(), nullable=False),
        sa.Column("ss_taxable_portion", sa.Text(), nullable=False),
        sa.Column("surplus", sa.Text(), nullable=False),
        sa.Column("ending_net_worth", sa.Text(), nullable=False),
        sa.UniqueConstraint("scenario_id", "year"),
    )
    op.create_index("ix_projection_year_scenario", "projection_year", ["scenario_id"])
    op.create_table(
        "projection_account_balance",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("scenario_id", sa.String(), sa.ForeignKey("scenario.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.String(), sa.ForeignKey("account.id"), nullable=False),
        sa.Column("beginning_balance", sa.Text(), nullable=False),
        sa.Column("contributions", sa.Text(), nullable=False),
        sa.Column("distributions", sa.Text(), nullable=False),
        sa.Column("investment_return", sa.Text(), nullable=False),
        sa.Column("ending_balance", sa.Text(), nullable=False),
        sa.UniqueConstraint("scenario_id", "year", "account_id"),
    )
    op.create_index("ix_pab_scenario_year", "projection_account_balance", ["scenario_id", "year"])
    op.create_index("ix_pab_account_year", "projection_account_balance", ["account_id", "year"])
    op.create_table(
        "projection_warning",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("scenario_id", sa.String(), sa.ForeignKey("scenario.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    for table_name in [
        "projection_warning",
        "projection_account_balance",
        "projection_year",
        "projection_run_metadata",
        "roth_conversion_plan",
        "sepp_plan",
        "withdrawal_strategy",
        "assumption_set",
        "expense_stream",
        "income_stream",
        "roth_conversion_lot",
        "roth_basis",
        "account",
        "scenario",
        "person",
        "household",
    ]:
        op.drop_table(table_name)
