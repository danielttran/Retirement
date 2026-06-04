"""Tests for rate-of-return-ordered drawdown and new account-type taxation."""
from __future__ import annotations

from decimal import Decimal

from planner_engine.common import AccountYearState, Person
from planner_engine.withdrawal import execute_withdrawals


def _person(age: int) -> Person:
    return Person("p1", dob_year=2024 - age, age_by_year={2024: age})


def test_lower_return_account_depleted_first_within_bucket() -> None:
    low = AccountYearState("low", "p1", "taxable_brokerage", Decimal("100000"), Decimal("0.03"),
                           cost_basis_pct=Decimal("1"))
    high = AccountYearState("high", "p1", "taxable_brokerage", Decimal("100000"), Decimal("0.09"),
                            cost_basis_pct=Decimal("1"))
    accounts = {"high": high, "low": low}
    result = execute_withdrawals(
        Decimal("50000"), accounts, ["taxable_brokerage"], 2024, [_person(50)], set()
    )
    assert result.withdrawn == Decimal("50000.00")
    # The low-return account should be drawn down first.
    assert low.balance == Decimal("50000.00")
    assert high.balance == Decimal("100000.00")


def test_deferred_comp_is_ordinary_income_no_penalty() -> None:
    dc = AccountYearState("dc", "p1", "deferred_comp", Decimal("100000"), Decimal("0"))
    result = execute_withdrawals(
        Decimal("20000"), {"dc": dc}, ["deferred_comp"], 2024, [_person(50)], set()
    )
    assert result.withdrawn == Decimal("20000.00")
    assert result.ordinary_income == Decimal("20000.00")
    assert result.penalty_eligible == Decimal("0.00")


def test_529_withdrawal_is_tax_free() -> None:
    plan = AccountYearState("529", "p1", "529", Decimal("50000"), Decimal("0"))
    result = execute_withdrawals(
        Decimal("10000"), {"529": plan}, ["529"], 2024, [_person(50)], set()
    )
    assert result.withdrawn == Decimal("10000.00")
    assert result.ordinary_income == Decimal("0.00")
