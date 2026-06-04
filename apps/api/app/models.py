from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, Money


class Household(Base):
    __tablename__ = "household"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    filing_status: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, default="MA", nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    people: Mapped[list[Person]] = relationship(
        back_populates="household", cascade="all, delete-orphan"
    )
    scenarios: Mapped[list[Scenario]] = relationship(
        back_populates="household", cascade="all, delete-orphan"
    )
    accounts: Mapped[list[Account]] = relationship(
        back_populates="household", cascade="all, delete-orphan"
    )
    income_streams: Mapped[list[IncomeStream]] = relationship(
        back_populates="household", cascade="all, delete-orphan"
    )
    expense_streams: Mapped[list[ExpenseStream]] = relationship(
        back_populates="household", cascade="all, delete-orphan"
    )


class Person(Base):
    __tablename__ = "person"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    household_id: Mapped[str] = mapped_column(ForeignKey("household.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    dob: Mapped[str] = mapped_column(String, nullable=False)
    retirement_date: Mapped[str | None] = mapped_column(String, nullable=True)
    life_expectancy_age: Mapped[int] = mapped_column(nullable=False)
    is_primary: Mapped[bool] = mapped_column(default=False, nullable=False)

    household: Mapped[Household] = relationship(back_populates="people")
    accounts: Mapped[list[Account]] = relationship(back_populates="owner")
    income_streams: Mapped[list[IncomeStream]] = relationship(back_populates="person")


class Account(Base):
    __tablename__ = "account"
    __table_args__ = (Index("ix_account_household", "household_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    household_id: Mapped[str] = mapped_column(ForeignKey("household.id"), nullable=False)
    owner_person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    account_type: Mapped[str] = mapped_column(String, nullable=False)
    current_balance: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    expected_return: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    return_stddev: Mapped[Decimal | None] = mapped_column(Money(), nullable=True)
    cost_basis_pct: Mapped[Decimal | None] = mapped_column(Money(), nullable=True)
    roth_first_contribution_year: Mapped[int | None] = mapped_column(nullable=True)
    is_governmental_457b: Mapped[bool] = mapped_column(default=False, nullable=False)
    has_rollover_basis_from_penalty_account: Mapped[bool] = mapped_column(
        default=False, nullable=False
    )
    rollover_basis_pct: Mapped[Decimal | None] = mapped_column(Money(), nullable=True)
    hsa_qualified_medical_expense_pct: Mapped[Decimal | None] = mapped_column(
        Money(), nullable=True
    )
    debt_annual_payment: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    exclude_from_withdrawals: Mapped[bool] = mapped_column(default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    household: Mapped[Household] = relationship(back_populates="accounts")
    owner: Mapped[Person] = relationship(back_populates="accounts")
    roth_basis: Mapped[RothBasis | None] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    roth_conversion_lots: Mapped[list[RothConversionLot]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class RothBasis(Base):
    __tablename__ = "roth_basis"

    account_id: Mapped[str] = mapped_column(ForeignKey("account.id"), primary_key=True)
    contributions_basis: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    conversions_basis: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    earnings_balance: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))

    account: Mapped[Account] = relationship(back_populates="roth_basis")


class RothConversionLot(Base):
    __tablename__ = "roth_conversion_lot"
    __table_args__ = (Index("ix_roth_conv_lot_account", "account_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id"), nullable=False)
    conversion_year: Mapped[int] = mapped_column(nullable=False)
    converted_amount: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    account: Mapped[Account] = relationship(back_populates="roth_conversion_lots")


class IncomeStream(Base):
    __tablename__ = "income_stream"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    household_id: Mapped[str] = mapped_column(ForeignKey("household.id"), nullable=False)
    person_id: Mapped[str | None] = mapped_column(ForeignKey("person.id"), nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    annual_amount: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    start_year: Mapped[int] = mapped_column(nullable=False)
    end_year: Mapped[int | None] = mapped_column(nullable=True)
    inflation_kind: Mapped[str] = mapped_column(String, nullable=False)
    custom_inflation_rate: Mapped[Decimal | None] = mapped_column(Money(), nullable=True)
    is_taxable_federal: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_taxable_state: Mapped[bool] = mapped_column(default=True, nullable=False)
    claiming_age: Mapped[int | None] = mapped_column(nullable=True)

    household: Mapped[Household] = relationship(back_populates="income_streams")
    person: Mapped[Person | None] = relationship(back_populates="income_streams")


class ExpenseStream(Base):
    __tablename__ = "expense_stream"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    household_id: Mapped[str] = mapped_column(ForeignKey("household.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    annual_amount: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    start_year: Mapped[int] = mapped_column(nullable=False)
    end_year: Mapped[int | None] = mapped_column(nullable=True)
    inflation_kind: Mapped[str] = mapped_column(String, nullable=False)
    custom_inflation_rate: Mapped[Decimal | None] = mapped_column(Money(), nullable=True)

    household: Mapped[Household] = relationship(back_populates="expense_streams")


class Scenario(Base):
    __tablename__ = "scenario"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    household_id: Mapped[str] = mapped_column(ForeignKey("household.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    parent_scenario_id: Mapped[str | None] = mapped_column(ForeignKey("scenario.id"))
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    household: Mapped[Household] = relationship(back_populates="scenarios")
    assumption_set: Mapped[AssumptionSet | None] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )
    withdrawal_strategy: Mapped[WithdrawalStrategy | None] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )
    sepp_plans: Mapped[list[SeppPlan]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )
    roth_conversion_plans: Mapped[list[RothConversionPlan]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )
    contributions: Mapped[list[Contribution]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )


class AssumptionSet(Base):
    __tablename__ = "assumption_set"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(
        ForeignKey("scenario.id"), unique=True, nullable=False
    )
    cpi_rate: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0.025"))
    healthcare_inflation_rate: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0.04"))
    ss_cola_rate: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0.025"))
    pension_cola_rate: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    bracket_indexing_rate: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0.025"))
    itemized_deductions: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    cash_reserve_target_months: Mapped[int] = mapped_column(default=24, nullable=False)
    irs_data_version: Mapped[str] = mapped_column(String, default="2024-33", nullable=False)
    engine_version: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, default="MA", nullable=False)
    tax_iteration_max: Mapped[int] = mapped_column(default=5, nullable=False)
    tax_iteration_tolerance: Mapped[Decimal] = mapped_column(Money(), default=Decimal("1.00"))

    scenario: Mapped[Scenario] = relationship(back_populates="assumption_set")


class WithdrawalStrategy(Base):
    __tablename__ = "withdrawal_strategy"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(
        ForeignKey("scenario.id"), unique=True, nullable=False
    )
    order_json: Mapped[str] = mapped_column(Text, nullable=False)
    surplus_target: Mapped[str] = mapped_column(String, default="taxable_brokerage", nullable=False)

    scenario: Mapped[Scenario] = relationship(back_populates="withdrawal_strategy")


class SeppPlan(Base):
    __tablename__ = "sepp_plan"
    __table_args__ = (
        Index(
            "ux_sepp_active_per_account",
            "account_id",
            unique=True,
            sqlite_where=text("status IN ('planned','active')"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenario.id"), nullable=False)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id"), nullable=False)
    method: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    valuation_date: Mapped[str] = mapped_column(String, nullable=False)
    first_payment_date: Mapped[str] = mapped_column(String, nullable=False)
    required_end_date: Mapped[str] = mapped_column(String, nullable=False)
    age_at_first_payment: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    account_balance_at_valuation: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    afr_prior_month: Mapped[Decimal | None] = mapped_column(Money(), nullable=True)
    afr_two_months_prior: Mapped[Decimal | None] = mapped_column(Money(), nullable=True)
    afr_month_used: Mapped[str | None] = mapped_column(String, nullable=True)
    selected_interest_rate: Mapped[Decimal | None] = mapped_column(Money(), nullable=True)
    max_allowed_interest_rate: Mapped[Decimal | None] = mapped_column(Money(), nullable=True)
    initial_life_expectancy_factor: Mapped[Decimal | None] = mapped_column(Money(), nullable=True)
    initial_annual_payment_locked: Mapped[Decimal | None] = mapped_column(Money(), nullable=True)
    irs_notice_version: Mapped[str] = mapped_column(
        String, default="Notice 2022-6", nullable=False
    )
    mortality_table_version: Mapped[str | None] = mapped_column(String, nullable=True)
    beneficiary_dob_snapshot: Mapped[str | None] = mapped_column(String, nullable=True)
    calculation_log_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_switched_to_rmd: Mapped[bool] = mapped_column(default=False, nullable=False)
    switched_to_rmd_year: Mapped[int | None] = mapped_column(nullable=True)

    scenario: Mapped[Scenario] = relationship(back_populates="sepp_plans")


class RothConversionPlan(Base):
    __tablename__ = "roth_conversion_plan"
    __table_args__ = (Index("ix_roth_conv_plan_scenario", "scenario_id", "year"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenario.id"), nullable=False)
    source_account_id: Mapped[str] = mapped_column(ForeignKey("account.id"), nullable=False)
    destination_account_id: Mapped[str] = mapped_column(ForeignKey("account.id"), nullable=False)
    year: Mapped[int] = mapped_column(nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    tax_payment_source_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("account.id"), nullable=True
    )

    scenario: Mapped[Scenario] = relationship(back_populates="roth_conversion_plans")


class Contribution(Base):
    __tablename__ = "contribution"
    __table_args__ = (Index("ix_contribution_scenario", "scenario_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenario.id"), nullable=False)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id"), nullable=False)
    annual_amount: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    start_year: Mapped[int] = mapped_column(nullable=False)
    end_year: Mapped[int | None] = mapped_column(nullable=True)
    inflation_kind: Mapped[str] = mapped_column(String, default="cpi", nullable=False)
    custom_inflation_rate: Mapped[Decimal | None] = mapped_column(Money(), nullable=True)
    employer_match_amount: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))

    scenario: Mapped[Scenario] = relationship(back_populates="contributions")


class ProjectionRunMetadata(Base):
    __tablename__ = "projection_run_metadata"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenario.id"), nullable=False)
    run_at: Mapped[str] = mapped_column(String, nullable=False)
    engine_version: Mapped[str] = mapped_column(String, nullable=False)
    irs_data_version: Mapped[str] = mapped_column(String, nullable=False)
    assumption_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    convergence_log_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProjectionYear(Base):
    __tablename__ = "projection_year"
    __table_args__ = (
        UniqueConstraint("scenario_id", "year"),
        Index("ix_projection_year_scenario", "scenario_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenario.id"), nullable=False)
    year: Mapped[int] = mapped_column(nullable=False)
    age_primary: Mapped[int] = mapped_column(nullable=False)
    age_spouse: Mapped[int | None] = mapped_column(nullable=True)
    gross_income: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    required_distributions: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    flexible_withdrawals: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    roth_conversions: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    expenses: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    federal_tax: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    state_tax: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    early_withdrawal_penalty: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    magi: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    provisional_income: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    ss_taxable_portion: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    ordinary_taxable_income: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    medicare_irmaa: Mapped[Decimal] = mapped_column(Money(), default=Decimal("0"))
    surplus: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    ending_net_worth: Mapped[Decimal] = mapped_column(Money(), nullable=False)


class ProjectionAccountBalance(Base):
    __tablename__ = "projection_account_balance"
    __table_args__ = (
        UniqueConstraint("scenario_id", "year", "account_id"),
        Index("ix_pab_scenario_year", "scenario_id", "year"),
        Index("ix_pab_account_year", "account_id", "year"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenario.id"), nullable=False)
    year: Mapped[int] = mapped_column(nullable=False)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id"), nullable=False)
    beginning_balance: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    contributions: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    distributions: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    investment_return: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    ending_balance: Mapped[Decimal] = mapped_column(Money(), nullable=False)


class ProjectionWarning(Base):
    __tablename__ = "projection_warning"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenario.id"), nullable=False)
    year: Mapped[int | None] = mapped_column(nullable=True)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
