"""Tests for the lifetime annuity calculator."""
from __future__ import annotations

from decimal import Decimal

from planner_engine.annuity import estimate_lifetime_annuity_income, payout_rate


def test_payout_rate_increases_with_age() -> None:
    assert payout_rate(60) < payout_rate(70) < payout_rate(80)


def test_payout_rate_interpolates() -> None:
    # Between 65 (0.060) and 70 (0.068), age 67 ≈ 0.0632
    rate = payout_rate(67)
    assert Decimal("0.060") < rate < Decimal("0.068")


def test_estimate_income() -> None:
    # 100000 premium at 65 → 0.06 → 6000
    assert estimate_lifetime_annuity_income(Decimal("100000"), 65) == Decimal("6000.00")


def test_payout_rate_clamps_at_bounds() -> None:
    assert payout_rate(40) == payout_rate(55)
    assert payout_rate(95) == payout_rate(85)
