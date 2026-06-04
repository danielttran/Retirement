"""Tests for the Monte Carlo / chance-of-success driver."""
from __future__ import annotations

from decimal import Decimal

from app.montecarlo import run_monte_carlo
from planner_engine.common import AccountYearState, Person
from planner_engine.projection import (
    AssumptionSet,
    ExpenseStream,
    IncomeStream,
    ScenarioInput,
)

IRS = "2024-33"
ENG = "test"


def _scenario(balance, expense, *, ret="0.06", stddev="0.10"):
    return ScenarioInput(
        id="s1",
        filing_status="single",
        state="MA",
        start_year=2024,
        end_year=2044,
        primary_person_id="p1",
        people=[Person("p1", dob_year=1959, age_by_year={y: y - 1959 for y in range(2024, 2045)})],
        accounts=[
            AccountYearState(
                "brk", "p1", "taxable_brokerage", Decimal(balance), Decimal(ret),
                cost_basis_pct=Decimal("0.8"), return_stddev=Decimal(stddev),
            )
        ],
        income_streams=[IncomeStream("ss", "social_security", Decimal("20000"), 2024,
                                     inflation_kind="none", person_id="p1")],
        expense_streams=[ExpenseStream("e", "must_spend", Decimal(expense), 2024,
                                       inflation_kind="none")],
        assumptions=AssumptionSet(cpi_rate=Decimal("0.025")),
    )


def test_monte_carlo_basic_shape() -> None:
    result = run_monte_carlo(_scenario("2000000", "40000"), IRS, ENG, trials=100, seed=1)
    assert result.trials == 100
    assert Decimal("0") <= result.chance_of_success <= Decimal("100")
    assert result.p10_estate <= result.p50_estate <= result.p90_estate


def test_monte_carlo_well_funded_higher_than_underfunded() -> None:
    rich = run_monte_carlo(_scenario("3000000", "40000"), IRS, ENG, trials=150, seed=7)
    poor = run_monte_carlo(_scenario("300000", "90000"), IRS, ENG, trials=150, seed=7)
    assert rich.chance_of_success > poor.chance_of_success


def test_monte_carlo_is_reproducible_with_seed() -> None:
    a = run_monte_carlo(_scenario("1000000", "50000"), IRS, ENG, trials=80, seed=42)
    b = run_monte_carlo(_scenario("1000000", "50000"), IRS, ENG, trials=80, seed=42)
    assert a.chance_of_success == b.chance_of_success
    assert a.p50_estate == b.p50_estate
