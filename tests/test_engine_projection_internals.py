"""Targeted tests to close remaining coverage gaps in planner_engine."""
from __future__ import annotations

from decimal import Decimal

import pytest
from planner_engine.common import AccountYearState, Person
from planner_engine.projection import (
    AssumptionSet,
    ExpenseStream,
    IncomeStream,
    ScenarioInput,
    SeppProjectionPlan,
    run_projection,
)
from planner_engine.projection.runner import (
    _expense_inflation_rate,
    _income_inflation_rate,
    _stream_active,
)
from planner_engine.rmd.engine import rmd_applicable_for_person
from planner_engine.roth import RothConversionPlan
from planner_engine.tax.engine import _required_decimal
from planner_engine.withdrawal.engine import (
    _account_matches_bucket,
    execute_withdrawals,
    withdraw_from_roth,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def person(pid: str, age: int, year: int = 2024) -> Person:
    return Person(id=pid, dob_year=year - age, age_by_year={year: age, year + 1: age + 1})


def account(
    account_id: str,
    account_type: str,
    balance: str,
    owner: str = "p1",
    expected_return: str = "0",
) -> AccountYearState:
    return AccountYearState(
        id=account_id,
        owner_person_id=owner,
        account_type=account_type,
        balance=Decimal(balance),
        expected_return=Decimal(expected_return),
    )


def scenario(
    accounts: list[AccountYearState],
    people: list[Person] | None = None,
    income_streams: list[IncomeStream] | None = None,
    expense_streams: list[ExpenseStream] | None = None,
    sepp_plans: list[SeppProjectionPlan] | None = None,
    roth_conversion_plans: list[RothConversionPlan] | None = None,
    end_year: int = 2024,
    assumptions: AssumptionSet | None = None,
) -> ScenarioInput:
    return ScenarioInput(
        id="s1",
        filing_status="single",
        state="MA",
        start_year=2024,
        end_year=end_year,
        primary_person_id="p1",
        people=people or [person("p1", 55)],
        accounts=accounts,
        income_streams=income_streams or [],
        expense_streams=expense_streams or [],
        assumptions=assumptions
        or AssumptionSet(tax_iteration_max=5, tax_iteration_tolerance=Decimal("1.00")),
        sepp_plans=sepp_plans or [],
        roth_conversion_plans=roth_conversion_plans or [],
    )


# ---------------------------------------------------------------------------
# runner.py — inflation routing (lines 500-519)
# ---------------------------------------------------------------------------

def test_income_inflation_ss_cola() -> None:
    assumptions = AssumptionSet(ss_cola_rate=Decimal("0.03"))
    stream = IncomeStream("s", "social_security", Decimal("10000"), 2024, inflation_kind="ss_cola")
    assert _income_inflation_rate(stream, assumptions) == Decimal("0.03")


def test_income_inflation_pension_cola() -> None:
    assumptions = AssumptionSet(pension_cola_rate=Decimal("0.02"))
    stream = IncomeStream("s", "pension", Decimal("5000"), 2024, inflation_kind="pension_cola")
    assert _income_inflation_rate(stream, assumptions) == Decimal("0.02")


def test_income_inflation_custom() -> None:
    assumptions = AssumptionSet()
    stream = IncomeStream(
        "s",
        "salary",
        Decimal("5000"),
        2024,
        inflation_kind="custom",
        custom_inflation_rate=Decimal("0.05"),
    )
    assert _income_inflation_rate(stream, assumptions) == Decimal("0.05")


def test_income_inflation_none() -> None:
    assumptions = AssumptionSet()
    stream = IncomeStream("s", "salary", Decimal("5000"), 2024, inflation_kind="none")
    assert _income_inflation_rate(stream, assumptions) == Decimal("0")


def test_income_inflation_cpi_default() -> None:
    assumptions = AssumptionSet(cpi_rate=Decimal("0.025"))
    stream = IncomeStream("s", "salary", Decimal("5000"), 2024, inflation_kind="cpi")
    assert _income_inflation_rate(stream, assumptions) == Decimal("0.025")


def test_expense_inflation_healthcare() -> None:
    assumptions = AssumptionSet(healthcare_inflation_rate=Decimal("0.04"))
    stream = ExpenseStream("s", "healthcare", Decimal("2000"), 2024, inflation_kind="healthcare")
    assert _expense_inflation_rate(stream, assumptions) == Decimal("0.04")


def test_expense_inflation_custom() -> None:
    assumptions = AssumptionSet()
    stream = ExpenseStream(
        "s",
        "must_spend",
        Decimal("2000"),
        2024,
        inflation_kind="custom",
        custom_inflation_rate=Decimal("0.03"),
    )
    assert _expense_inflation_rate(stream, assumptions) == Decimal("0.03")


def test_expense_inflation_none() -> None:
    assumptions = AssumptionSet()
    stream = ExpenseStream("s", "must_spend", Decimal("2000"), 2024, inflation_kind="none")
    assert _expense_inflation_rate(stream, assumptions) == Decimal("0")


# ---------------------------------------------------------------------------
# runner.py — stream_active with inactive streams and SS claiming age (lines 443-448)
# ---------------------------------------------------------------------------

def test_stream_active_before_start() -> None:
    assert _stream_active(2025, None, 2024) is False


def test_stream_active_after_end() -> None:
    assert _stream_active(2020, 2023, 2024) is False


def test_inactive_income_stream_excluded_from_projection() -> None:
    """Stream ending before projection year contributes nothing."""
    run = run_projection(
        scenario(
            [account("cash", "cash", "100000")],
            income_streams=[
                # Stream ends before start_year — should be ignored
                IncomeStream(
                    "s", "salary", Decimal("50000"), 2020, end_year=2023, inflation_kind="none"
                )
            ],
        ),
        "2024-33",
        "test",
    )
    assert run.years[0].gross_income == Decimal("0.00")


def test_ss_claiming_age_not_reached_excluded() -> None:
    """SS stream with claiming_age=67 is excluded when person is age 55."""
    p = person("p1", 55)
    run = run_projection(
        scenario(
            [account("cash", "cash", "100000")],
            people=[p],
            income_streams=[
                IncomeStream(
                    "ss",
                    "social_security",
                    Decimal("24000"),
                    2024,
                    inflation_kind="none",
                    person_id="p1",
                    claiming_age=67,
                )
            ],
        ),
        "2024-33",
        "test",
    )
    # person is 55, claiming_age=67 → SS not yet payable
    assert run.years[0].gross_income == Decimal("0.00")


# ---------------------------------------------------------------------------
# runner.py — SEPP underfunded warning (lines 543-560)
# ---------------------------------------------------------------------------

def test_sepp_underfunded_triggers_warning() -> None:
    """SEPP account with less balance than annual payment generates error warning."""
    ira = account("ira", "traditional_ira", "500")  # less than annual payment
    cash = account("cash", "cash", "10000")
    run = run_projection(
        scenario(
            [ira, cash],
            sepp_plans=[
                SeppProjectionPlan(
                    "sepp1", "ira", "fixed_amortization", "active", 2024, 2030, Decimal("1000")
                )
            ],
        ),
        "2024-33",
        "test",
    )
    codes = {w.code for w in run.warnings}
    assert "projection_required_distribution_unfunded" in codes


def test_sepp_inactive_plan_not_taken() -> None:
    """A completed SEPP plan contributes no distributions."""
    ira = account("ira", "traditional_ira", "50000")
    run = run_projection(
        scenario(
            [ira, account("cash", "cash", "0")],
            sepp_plans=[
                SeppProjectionPlan(
                    "sepp1", "ira", "fixed_amortization", "completed", 2024, 2030, Decimal("5000")
                )
            ],
        ),
        "2024-33",
        "test",
    )
    assert run.years[0].required_distributions == Decimal("0.00")


# ---------------------------------------------------------------------------
# runner.py — RMD underfunded warning (lines 582-592)
# ---------------------------------------------------------------------------

def test_rmd_underfunded_triggers_warning() -> None:
    """SEPP drains IRA live balance below the beginning-of-year RMD snapshot amount."""
    owner = Person("p1", dob_year=1951, age_by_year={2024: 73})
    # Age 73 → RMD factor 26.5. Balance $265 → RMD = $10.00.
    # SEPP payment $260 runs before RMD, leaving live balance $5 < RMD $10 → warning.
    ira = account("ira", "traditional_ira", "265")
    run = run_projection(
        scenario(
            [ira, account("cash", "cash", "0")],
            people=[owner],
            sepp_plans=[
                SeppProjectionPlan(
                    "sepp1", "ira", "fixed_amortization", "active", 2024, 2030, Decimal("260")
                )
            ],
        ),
        "2024-33",
        "test",
    )
    codes = {w.code for w in run.warnings}
    assert "projection_required_distribution_unfunded" in codes


# ---------------------------------------------------------------------------
# runner.py — surplus fully consumed by cash reserve (line 639)
# ---------------------------------------------------------------------------

def test_surplus_fully_consumed_by_cash_reserve() -> None:
    """Surplus exactly fills cash reserve; no remainder routed to brokerage."""
    # Cash target = 24 months * 100/12 = $200 of must_spend
    # Cash has 0; income 200; expense 100; income - expense - taxes > 0 (surplus)
    # surplus routes to cash; cash was at 0, target 200; so cash gets topped up to 200
    # and remaining = 0 → early return on line 639
    cash = account("cash", "cash", "0")
    taxable = account("taxable", "taxable_brokerage", "0")
    run = run_projection(
        scenario(
            [cash, taxable],
            income_streams=[
                IncomeStream("salary", "salary", Decimal("5000"), 2024, inflation_kind="none")
            ],
            expense_streams=[
                ExpenseStream("rent", "must_spend", Decimal("100"), 2024, inflation_kind="none")
            ],
            assumptions=AssumptionSet(
                tax_iteration_max=5,
                tax_iteration_tolerance=Decimal("1.00"),
                cash_reserve_target_months=24,
            ),
        ),
        "2024-33",
        "test",
    )
    balances = {row.account_id: row for row in run.account_balances}
    # cash should have gotten the surplus (expense-based cash reserve target is tiny)
    assert balances["cash"].ending_balance > Decimal("0")


# ---------------------------------------------------------------------------
# runner.py — tax non-convergence warning (lines 238-248 and 399)
# ---------------------------------------------------------------------------

def test_non_convergence_warning_with_max_iterations_zero() -> None:
    """tax_iteration_max=0 forces non-convergence when there is a funding gap."""
    assumptions = AssumptionSet(
        tax_iteration_max=0, tax_iteration_tolerance=Decimal("1.00")
    )
    # expense > income → funding gap always exists → loop exhausts after 1 iteration
    run = run_projection(
        scenario(
            [account("cash", "cash", "100000")],
            expense_streams=[
                ExpenseStream("big", "must_spend", Decimal("50000"), 2024, inflation_kind="none")
            ],
            assumptions=assumptions,
        ),
        "2024-33",
        "test",
    )
    codes = {w.code for w in run.warnings}
    assert "projection_tax_convergence_max" in codes


# ---------------------------------------------------------------------------
# rmd/engine.py — rmd_applicable_for_person (lines 22-25)
# ---------------------------------------------------------------------------

def test_rmd_applicable_for_person_at_applicable_age() -> None:
    # DOB 1960 → applicable age 75; at age 75 should be applicable
    p = Person("p1", dob_year=1960, age_by_year={2035: 75})
    assert rmd_applicable_for_person(p, 2035, "2024-33") is True


def test_rmd_not_applicable_before_applicable_age() -> None:
    p = Person("p1", dob_year=1960, age_by_year={2034: 74})
    assert rmd_applicable_for_person(p, 2034, "2024-33") is False


# ---------------------------------------------------------------------------
# tax/engine.py — _required_decimal(None) raises ValueError (line 173)
# ---------------------------------------------------------------------------

def test_required_decimal_raises_on_none() -> None:
    with pytest.raises(ValueError, match="Expected Decimal value"):
        _required_decimal(None)


# ---------------------------------------------------------------------------
# withdrawal/engine.py — inner break when remaining hits 0 (line 65)
# ---------------------------------------------------------------------------

def test_withdrawal_stops_when_remaining_satisfied() -> None:
    """Two cash accounts: first satisfies full request, second never touched."""
    acct1 = account("c1", "cash", "1000")
    acct2 = account("c2", "cash", "1000")
    p = person("p1", 50)
    result = execute_withdrawals(
        Decimal("500"),
        {"c1": acct1, "c2": acct2},
        ["cash"],
        2024,
        [p],
        set(),
    )
    assert result.withdrawn == Decimal("500.00")
    # Only the first account was touched (line 65 break kicks in)
    assert acct1.balance == Decimal("500")
    assert acct2.balance == Decimal("1000")


# ---------------------------------------------------------------------------
# withdrawal/engine.py — _account_matches_bucket fallback (line 103)
# ---------------------------------------------------------------------------

def test_account_matches_bucket_fallback_governmental_457b() -> None:
    acct = account("a1", "governmental_457b", "5000")
    # "governmental_457b" is not a named bucket — falls through to type comparison
    assert _account_matches_bucket(acct, "governmental_457b") is True
    assert _account_matches_bucket(acct, "cash") is False


# ---------------------------------------------------------------------------
# withdrawal/engine.py — traditional penalty under age 59 (lines 125-127)
# ---------------------------------------------------------------------------

def test_traditional_withdrawal_before_59_incurs_penalty() -> None:
    """Traditional IRA withdrawal at age 50 should be fully penalty-eligible."""
    acct = account("ira", "traditional_ira", "20000")
    p = person("p1", 50)
    result = execute_withdrawals(
        Decimal("5000"),
        {"ira": acct},
        ["traditional"],
        2024,
        [p],
        set(),
    )
    assert result.withdrawn == Decimal("5000.00")
    assert result.penalty_eligible == Decimal("5000.00")
    assert result.ordinary_income == Decimal("5000.00")


def test_traditional_withdrawal_at_60_no_penalty() -> None:
    acct = account("ira", "traditional_ira", "20000")
    p = person("p1", 60)
    result = execute_withdrawals(
        Decimal("5000"),
        {"ira": acct},
        ["traditional"],
        2024,
        [p],
        set(),
    )
    assert result.penalty_eligible == Decimal("0.00")


# ---------------------------------------------------------------------------
# withdrawal/engine.py — withdraw_from_roth with layer="earnings" (line 164)
# ---------------------------------------------------------------------------

def test_withdraw_roth_earnings_layer_directly() -> None:
    """Calling withdraw_from_roth with layer='earnings' covers line 164."""
    acct = AccountYearState(
        id="roth1",
        owner_person_id="p1",
        account_type="roth_ira",
        balance=Decimal("15000"),
        expected_return=Decimal("0"),
        roth_first_contribution_year=2010,
        roth_earnings_balance=Decimal("15000"),
    )
    p = person("p1", 62)
    line = withdraw_from_roth(acct, Decimal("5000"), 2024, p, "earnings")
    assert line.amount == Decimal("5000.00")
    assert line.layer == "roth_earnings"
    # Age 62 and 5-year clock satisfied (2010 + 5 = 2015 ≤ 2024) → qualified
    assert line.ordinary_income == Decimal("0.00")
    assert line.penalty_eligible == Decimal("0.00")
