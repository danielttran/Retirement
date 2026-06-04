"""Tests for the Roth Conversion Explorer."""
from __future__ import annotations

from decimal import Decimal

from app.roth_explorer import suggest_roth_conversions
from planner_engine.common import AccountYearState, Person
from planner_engine.projection import (
    AssumptionSet,
    ExpenseStream,
    IncomeStream,
    ScenarioInput,
)

IRS = "2024-33"
ENG = "test"


def _scenario():
    return ScenarioInput(
        id="s1",
        filing_status="single",
        state="MA",
        start_year=2024,
        end_year=2030,
        primary_person_id="p1",
        people=[Person("p1", dob_year=1962, age_by_year={y: y - 1962 for y in range(2024, 2031)})],
        accounts=[
            AccountYearState("ira", "p1", "traditional_ira", Decimal("800000"), Decimal("0.05")),
            AccountYearState(
                "roth", "p1", "roth_ira", Decimal("0"), Decimal("0.05"),
                roth_first_contribution_year=2010,
            ),
            AccountYearState("cash", "p1", "cash", Decimal("200000"), Decimal("0")),
        ],
        income_streams=[
            IncomeStream("ss", "social_security", Decimal("24000"), 2024,
                         inflation_kind="none", person_id="p1", claiming_age=62),
        ],
        expense_streams=[
            ExpenseStream("e", "must_spend", Decimal("40000"), 2024, inflation_kind="none")
        ],
        assumptions=AssumptionSet(cpi_rate=Decimal("0.025")),
    )


def test_bracket_fill_suggests_conversions() -> None:
    result = suggest_roth_conversions(
        _scenario(), IRS, ENG, strategy="bracket", target_rate=Decimal("0.22"),
        irmaa_magi_ceiling=Decimal("0"), start_year=2024, end_year=2030,
    )
    assert result.suggestions, "expected bracket-fill suggestions"
    assert result.total_converted > Decimal("0")
    # Each suggested conversion should be capped at the 22% bracket headroom (positive).
    for s in result.suggestions:
        assert s.amount > Decimal("0")
        assert s.amount <= s.traditional_balance


def test_explorer_needs_roth_account() -> None:
    sc = _scenario()
    sc_no_roth = ScenarioInput(
        id=sc.id, filing_status=sc.filing_status, state=sc.state,
        start_year=sc.start_year, end_year=sc.end_year, primary_person_id=sc.primary_person_id,
        people=sc.people,
        accounts=[a for a in sc.accounts if a.account_type != "roth_ira"],
        income_streams=sc.income_streams, expense_streams=sc.expense_streams,
        assumptions=sc.assumptions,
    )
    result = suggest_roth_conversions(
        sc_no_roth, IRS, ENG, strategy="bracket", target_rate=Decimal("0.22"),
        irmaa_magi_ceiling=Decimal("0"), start_year=2024, end_year=2030,
    )
    assert result.suggestions == []
    assert result.note is not None


def test_irmaa_strategy_caps_magi() -> None:
    result = suggest_roth_conversions(
        _scenario(), IRS, ENG, strategy="irmaa", target_rate=Decimal("0"),
        irmaa_magi_ceiling=Decimal("103000"), start_year=2024, end_year=2030,
    )
    # Conversions should keep suggested MAGI headroom below the IRMAA ceiling.
    for s in result.suggestions:
        assert s.magi <= Decimal("103000")
