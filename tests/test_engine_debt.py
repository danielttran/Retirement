"""Tests for debt/mortgage modeling and account exclusion (Boldin parity)."""
from __future__ import annotations

from decimal import Decimal

from planner_engine.common import AccountYearState, Person
from planner_engine.projection import (
    AssumptionSet,
    ExpenseStream,
    IncomeStream,
    ScenarioInput,
    run_projection,
)

IRS_VERSION = "2024-33"
ENGINE_VERSION = "test"


def _run(accounts, *, income=Decimal("0"), expenses=Decimal("0"), end_year=2026):
    return run_projection(
        ScenarioInput(
            id="s1",
            filing_status="single",
            state="MA",
            start_year=2024,
            end_year=end_year,
            primary_person_id="p1",
            people=[
                Person("p1", dob_year=1969, age_by_year={y: y - 1969 for y in range(2024, 2050)})
            ],
            accounts=accounts,
            income_streams=(
                [IncomeStream("s", "salary", income, 2024, inflation_kind="none")]
                if income > 0
                else []
            ),
            expense_streams=(
                [ExpenseStream("e", "must_spend", expenses, 2024, inflation_kind="none")]
                if expenses > 0
                else []
            ),
            assumptions=AssumptionSet(tax_iteration_max=5, tax_iteration_tolerance=Decimal("1.00")),
        ),
        IRS_VERSION,
        ENGINE_VERSION,
    )


def test_debt_reduces_net_worth() -> None:
    cash = AccountYearState("cash", "p1", "cash", Decimal("100000"), Decimal("0"))
    debt = AccountYearState("loan", "p1", "debt", Decimal("30000"), Decimal("0"))
    run = _run([cash, debt], end_year=2024)
    # Net worth = 100k cash - 30k debt = 70k
    assert run.years[0].ending_net_worth == Decimal("70000.00")


def test_debt_amortizes_with_payment_and_interest() -> None:
    cash = AccountYearState("cash", "p1", "cash", Decimal("500000"), Decimal("0"))
    # 30k loan at 10% APR, 11k/yr payment.
    debt = AccountYearState(
        "loan", "p1", "debt", Decimal("30000"), Decimal("0.10"),
        debt_annual_payment=Decimal("11000"),
    )
    run = _run([cash, debt], income=Decimal("50000"), end_year=2024)
    loan_bal = next(b for b in run.account_balances if b.account_id == "loan")
    # Year: principal 30000 - 11000 payment = 19000, then +10% interest = 20900
    assert loan_bal.distributions == Decimal("11000.00")
    assert loan_bal.ending_balance == Decimal("20900.00")


def test_debt_pays_off_and_stops() -> None:
    cash = AccountYearState("cash", "p1", "cash", Decimal("500000"), Decimal("0"))
    debt = AccountYearState(
        "loan", "p1", "debt", Decimal("5000"), Decimal("0"),
        debt_annual_payment=Decimal("11000"),
    )
    run = _run([cash, debt], income=Decimal("50000"), end_year=2025)
    balances = {(b.account_id, b.year): b for b in run.account_balances}
    # Year 1 pays the full 5000 (capped at balance), year 2 pays nothing.
    assert balances[("loan", 2024)].distributions == Decimal("5000.00")
    assert balances[("loan", 2024)].ending_balance == Decimal("0.00")
    assert balances[("loan", 2025)].distributions == Decimal("0.00")


def test_exclude_from_withdrawals_protects_account() -> None:
    # Need 40k for expenses; cash is excluded so the brokerage must fund it.
    cash = AccountYearState(
        "cash", "p1", "cash", Decimal("100000"), Decimal("0"), exclude_from_withdrawals=True
    )
    brokerage = AccountYearState(
        "brk", "p1", "taxable_brokerage", Decimal("100000"), Decimal("0"),
        cost_basis_pct=Decimal("1"),
    )
    run = _run([cash, brokerage], expenses=Decimal("40000"), end_year=2024)
    cash_bal = next(b for b in run.account_balances if b.account_id == "cash")
    brk_bal = next(b for b in run.account_balances if b.account_id == "brk")
    assert cash_bal.ending_balance == Decimal("100000.00")  # untouched
    assert brk_bal.ending_balance < Decimal("100000.00")  # funded the gap


def test_home_sale_moves_net_proceeds_to_cash() -> None:
    cash = AccountYearState("cash", "p1", "cash", Decimal("10000"), Decimal("0"))
    home = AccountYearState(
        "home", "p1", "real_estate", Decimal("500000"), Decimal("0"),
        sale_year=2025, selling_cost_pct=Decimal("0.06"),
    )
    run = _run([cash, home], end_year=2026)
    balances = {(b.account_id, b.year): b for b in run.account_balances}
    assert balances[("home", 2024)].ending_balance == Decimal("500000.00")
    assert balances[("home", 2025)].ending_balance == Decimal("0.00")
    assert balances[("home", 2025)].distributions == Decimal("500000.00")
    assert balances[("cash", 2025)].ending_balance == Decimal("480000.00")
