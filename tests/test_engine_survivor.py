"""Tests for survivor / death-of-spouse modeling."""
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

IRS = "2024-33"
ENG = "test"


def _couple_scenario(streams):
    # A dies at 2026 (age 82, dob 1944), B lives to 2030 (dob 1948).
    a = Person("a", dob_year=1944, death_year=2026)
    b = Person("b", dob_year=1948, death_year=2030)
    return ScenarioInput(
        id="s1",
        filing_status="mfj",
        state="MA",
        start_year=2024,
        end_year=2030,
        primary_person_id="a",
        spouse_person_id="b",
        people=[a, b],
        accounts=[AccountYearState("cash", "a", "cash", Decimal("2000000"), Decimal("0"))],
        income_streams=streams,
        expense_streams=[
            ExpenseStream("e", "must_spend", Decimal("40000"), 2024, inflation_kind="none")
        ],
        assumptions=AssumptionSet(),
    )


def test_deceased_salary_stops() -> None:
    streams = [
        IncomeStream("sal", "salary", Decimal("50000"), 2024, inflation_kind="none", person_id="a"),
    ]
    run = run_projection(_couple_scenario(streams), IRS, ENG)
    by_year = {y.year: y for y in run.years}
    assert by_year[2026].gross_income == Decimal("50000.00")  # A alive in death year
    assert by_year[2027].gross_income == Decimal("0.00")  # A's salary stops after death


def test_pension_survivor_pct_applies() -> None:
    streams = [
        IncomeStream(
            "pen", "pension", Decimal("40000"), 2024, inflation_kind="none",
            person_id="a", survivor_pct=Decimal("0.5"),
        ),
    ]
    run = run_projection(_couple_scenario(streams), IRS, ENG)
    by_year = {y.year: y for y in run.years}
    assert by_year[2026].gross_income == Decimal("40000.00")  # full while A alive
    assert by_year[2027].gross_income == Decimal("20000.00")  # 50% survivor benefit


def test_social_security_survivor_takes_higher_benefit() -> None:
    streams = [
        IncomeStream("ssa", "social_security", Decimal("40000"), 2024, inflation_kind="none",
                     person_id="a", claiming_age=70),
        IncomeStream("ssb", "social_security", Decimal("24000"), 2024, inflation_kind="none",
                     person_id="b", claiming_age=70),
    ]
    run = run_projection(_couple_scenario(streams), IRS, ENG)
    by_year = {y.year: y for y in run.years}
    # Both alive 2026: 40000 + 24000 = 64000
    assert by_year[2026].gross_income == Decimal("64000.00")
    # 2027: A dead — survivor B receives max(24000, 40000) = 40000
    assert by_year[2027].gross_income == Decimal("40000.00")


def test_single_person_unaffected() -> None:
    p = Person("p1", dob_year=1959, death_year=2030)
    sc = ScenarioInput(
        id="s1", filing_status="single", state="MA", start_year=2024, end_year=2030,
        primary_person_id="p1", people=[p],
        accounts=[AccountYearState("cash", "p1", "cash", Decimal("1000000"), Decimal("0"))],
        income_streams=[
            IncomeStream("sal", "salary", Decimal("30000"), 2024, inflation_kind="none",
                         person_id="p1")
        ],
        expense_streams=[],
        assumptions=AssumptionSet(),
    )
    run = run_projection(sc, IRS, ENG)
    assert all(y.gross_income == Decimal("30000.00") for y in run.years)
