"""Tests for accumulation-phase contributions + employer match (Boldin parity)."""
from __future__ import annotations

from decimal import Decimal

from planner_engine.common import AccountYearState, Person
from planner_engine.projection import (
    AssumptionSet,
    ContributionPlan,
    ExpenseStream,
    IncomeStream,
    ScenarioInput,
    run_projection,
)

IRS_VERSION = "2024-33"
ENGINE_VERSION = "test"


def _scenario(accounts, contributions, income=Decimal("100000"), expenses=Decimal("40000")):
    return ScenarioInput(
        id="s1",
        filing_status="single",
        state="MA",
        start_year=2024,
        end_year=2024,
        primary_person_id="p1",
        people=[Person("p1", dob_year=1979, age_by_year={2024: 45})],
        accounts=accounts,
        income_streams=[IncomeStream("salary", "salary", income, 2024, inflation_kind="none")],
        expense_streams=[
            ExpenseStream("living", "must_spend", expenses, 2024, inflation_kind="none")
        ],
        assumptions=AssumptionSet(tax_iteration_max=5, tax_iteration_tolerance=Decimal("1.00")),
        contribution_plans=contributions,
    )


def test_pretax_401k_contribution_grows_account_and_reduces_wages() -> None:
    cash = AccountYearState("cash", "p1", "cash", Decimal("10000"), Decimal("0"))
    k401 = AccountYearState("k", "p1", "traditional_401k", Decimal("0"), Decimal("0"))
    no_contrib = run_projection(_scenario([cash, k401], []), IRS_VERSION, ENGINE_VERSION)
    with_contrib = run_projection(
        _scenario(
            [
                AccountYearState("cash", "p1", "cash", Decimal("10000"), Decimal("0")),
                AccountYearState("k", "p1", "traditional_401k", Decimal("0"), Decimal("0")),
            ],
            [ContributionPlan("k", Decimal("20000"), 2024, inflation_kind="none")],
        ),
        IRS_VERSION,
        ENGINE_VERSION,
    )
    # 401k should hold the contribution
    k_bal = next(b for b in with_contrib.account_balances if b.account_id == "k")
    assert k_bal.ending_balance == Decimal("20000.00")
    assert k_bal.contributions == Decimal("20000.00")
    # Pre-tax contribution lowers federal tax versus no contribution
    assert with_contrib.years[0].federal_tax < no_contrib.years[0].federal_tax


def test_employer_match_is_free_money() -> None:
    cash = AccountYearState("cash", "p1", "cash", Decimal("0"), Decimal("0"))
    k401 = AccountYearState("k", "p1", "traditional_401k", Decimal("0"), Decimal("0"))
    run = run_projection(
        _scenario(
            [cash, k401],
            [
                ContributionPlan(
                    "k",
                    Decimal("10000"),
                    2024,
                    inflation_kind="none",
                    employer_match_amount=Decimal("5000"),
                )
            ],
        ),
        IRS_VERSION,
        ENGINE_VERSION,
    )
    k_bal = next(b for b in run.account_balances if b.account_id == "k")
    assert k_bal.ending_balance == Decimal("15000.00")  # 10k employee + 5k match


def test_roth_contribution_adds_basis_not_wage_reduction() -> None:
    cash = AccountYearState("cash", "p1", "cash", Decimal("0"), Decimal("0"))
    roth = AccountYearState(
        "r", "p1", "roth_ira", Decimal("0"), Decimal("0"), roth_first_contribution_year=2024
    )
    no_contrib = run_projection(_scenario([cash, roth], []), IRS_VERSION, ENGINE_VERSION)
    run = run_projection(
        _scenario(
            [
                AccountYearState("cash", "p1", "cash", Decimal("0"), Decimal("0")),
                AccountYearState(
                    "r",
                    "p1",
                    "roth_ira",
                    Decimal("0"),
                    Decimal("0"),
                    roth_first_contribution_year=2024,
                ),
            ],
            [ContributionPlan("r", Decimal("7000"), 2024, inflation_kind="none")],
        ),
        IRS_VERSION,
        ENGINE_VERSION,
    )
    r_bal = next(b for b in run.account_balances if b.account_id == "r")
    assert r_bal.ending_balance == Decimal("7000.00")
    # Roth is after-tax: no wage reduction, so federal tax unchanged
    assert run.years[0].federal_tax == no_contrib.years[0].federal_tax


def test_contribution_capped_at_available_income() -> None:
    # Income 30k, expenses 40k → nothing available; engine must not withdraw to fund a contribution.
    cash = AccountYearState("cash", "p1", "cash", Decimal("100000"), Decimal("0"))
    k401 = AccountYearState("k", "p1", "traditional_401k", Decimal("0"), Decimal("0"))
    run = run_projection(
        _scenario(
            [cash, k401],
            [ContributionPlan("k", Decimal("20000"), 2024, inflation_kind="none")],
            income=Decimal("30000"),
            expenses=Decimal("40000"),
        ),
        IRS_VERSION,
        ENGINE_VERSION,
    )
    k_bal = next(b for b in run.account_balances if b.account_id == "k")
    assert k_bal.contributions == Decimal("0.00")


def test_contribution_conservation_holds() -> None:
    cash = AccountYearState("cash", "p1", "cash", Decimal("50000"), Decimal("0.05"))
    k401 = AccountYearState("k", "p1", "traditional_401k", Decimal("0"), Decimal("0.06"))
    run = run_projection(
        _scenario(
            [cash, k401],
            [
                ContributionPlan(
                    "k",
                    Decimal("15000"),
                    2024,
                    inflation_kind="none",
                    employer_match_amount=Decimal("7500"),
                )
            ],
        ),
        IRS_VERSION,
        ENGINE_VERSION,
    )
    for ab in run.account_balances:
        reconstructed = (
            ab.beginning_balance + ab.contributions - ab.distributions + ab.investment_return
        )
        assert abs(reconstructed - ab.ending_balance) <= Decimal("0.01")


def test_projection_summary_metrics() -> None:
    cash = AccountYearState("cash", "p1", "cash", Decimal("100000"), Decimal("0"))
    run = run_projection(
        ScenarioInput(
            id="s1",
            filing_status="single",
            state="MA",
            start_year=2024,
            end_year=2027,
            primary_person_id="p1",
            people=[
                Person("p1", dob_year=1959, age_by_year={2024: 65, 2025: 66, 2026: 67, 2027: 68})
            ],
            accounts=[cash],
            income_streams=[],
            expense_streams=[
                ExpenseStream("living", "must_spend", Decimal("60000"), 2024, inflation_kind="none")
            ],
            assumptions=AssumptionSet(tax_iteration_max=5, tax_iteration_tolerance=Decimal("1.00")),
        ),
        IRS_VERSION,
        ENGINE_VERSION,
    )
    summary = run.summary
    assert summary.final_year == 2027
    # 100k cash drained by 60k/yr expenses → out of savings in year 2 (2025).
    assert summary.out_of_savings_year == 2025
    assert summary.out_of_savings_age == 66
    assert summary.estate_net_worth <= Decimal("0")
    assert summary.total_lifetime_expenses == Decimal("240000.00")
