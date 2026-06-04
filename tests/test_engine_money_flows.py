"""Tests for Money Flows (manual scheduled transfers)."""
from __future__ import annotations

from decimal import Decimal

from planner_engine.common import AccountYearState, Person
from planner_engine.projection import (
    AssumptionSet,
    MoneyFlowPlan,
    ScenarioInput,
    run_projection,
)

IRS = "2024-33"
ENG = "test"


def _sc(accounts, flows, end_year=2024):
    return ScenarioInput(
        id="s1", filing_status="single", state="MA", start_year=2024, end_year=end_year,
        primary_person_id="p1",
        people=[Person("p1", dob_year=1969, age_by_year={y: y - 1969 for y in range(2024, 2031)})],
        accounts=accounts, money_flows=flows, assumptions=AssumptionSet(),
    )


def test_transfer_moves_balance_between_assets() -> None:
    cash = AccountYearState("cash", "p1", "cash", Decimal("100000"), Decimal("0"))
    brk = AccountYearState("brk", "p1", "taxable_brokerage", Decimal("0"), Decimal("0"),
                           cost_basis_pct=Decimal("1"))
    run = run_projection(
        _sc([cash, brk], [MoneyFlowPlan("cash", "brk", 2024, Decimal("30000"))]),
        IRS, ENG,
    )
    bals = {b.account_id: b for b in run.account_balances}
    assert bals["cash"].ending_balance == Decimal("70000.00")
    assert bals["brk"].ending_balance == Decimal("30000.00")
    # Cash source → tax-free
    assert run.years[0].federal_tax == Decimal("0.00")


def test_traditional_source_is_taxed_as_ordinary() -> None:
    ira = AccountYearState("ira", "p1", "traditional_ira", Decimal("100000"), Decimal("0"))
    cash = AccountYearState("cash", "p1", "cash", Decimal("50000"), Decimal("0"))
    run = run_projection(
        _sc([ira, cash], [MoneyFlowPlan("ira", "cash", 2024, Decimal("40000"))]),
        IRS, ENG,
    )
    # Moving 40k out of a traditional IRA realizes 40k ordinary income → federal tax > 0.
    assert run.years[0].federal_tax > Decimal("0.00")


def test_debt_paydown_via_money_flow() -> None:
    cash = AccountYearState("cash", "p1", "cash", Decimal("100000"), Decimal("0"))
    loan = AccountYearState("loan", "p1", "debt", Decimal("25000"), Decimal("0"))
    run = run_projection(
        _sc([cash, loan], [MoneyFlowPlan("cash", "loan", 2024, Decimal("25000"))]),
        IRS, ENG,
    )
    bals = {b.account_id: b for b in run.account_balances}
    assert bals["loan"].ending_balance == Decimal("0.00")
    assert bals["cash"].ending_balance == Decimal("75000.00")
    # Net worth = 75k cash - 0 debt = 75k (was 100k - 25k = 75k): unchanged by paydown.
    assert run.years[0].ending_net_worth == Decimal("75000.00")


def test_money_flow_conservation() -> None:
    cash = AccountYearState("cash", "p1", "cash", Decimal("100000"), Decimal("0.05"))
    brk = AccountYearState("brk", "p1", "taxable_brokerage", Decimal("10000"), Decimal("0.06"),
                           cost_basis_pct=Decimal("0.8"))
    run = run_projection(
        _sc([cash, brk], [MoneyFlowPlan("cash", "brk", 2024, Decimal("20000"))]),
        IRS, ENG,
    )
    for ab in run.account_balances:
        recon = ab.beginning_balance + ab.contributions - ab.distributions + ab.investment_return
        assert abs(recon - ab.ending_balance) <= Decimal("0.01")
