"""Lifetime (immediate single-life) annuity income calculator.

Pure Decimal. Estimates the annual income a single-premium immediate annuity (SPIA) would pay,
using an age-based payout-rate table (interpolated). A simplified national estimate.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")

# Approximate single-life immediate-annuity payout rates (annual income / premium) by age.
_PAYOUT_RATES: list[tuple[int, Decimal]] = [
    (55, Decimal("0.050")),
    (60, Decimal("0.055")),
    (65, Decimal("0.060")),
    (70, Decimal("0.068")),
    (75, Decimal("0.078")),
    (80, Decimal("0.090")),
    (85, Decimal("0.105")),
]


def payout_rate(age: int) -> Decimal:
    """Interpolated SPIA payout rate for a given purchase age."""
    if age <= _PAYOUT_RATES[0][0]:
        return _PAYOUT_RATES[0][1]
    if age >= _PAYOUT_RATES[-1][0]:
        return _PAYOUT_RATES[-1][1]
    for (lo_age, lo_rate), (hi_age, hi_rate) in zip(
        _PAYOUT_RATES, _PAYOUT_RATES[1:], strict=False
    ):
        if lo_age <= age <= hi_age:
            span = Decimal(hi_age - lo_age)
            frac = Decimal(age - lo_age) / span
            return lo_rate + (hi_rate - lo_rate) * frac
    return _PAYOUT_RATES[-1][1]


def estimate_lifetime_annuity_income(premium: Decimal, age: int) -> Decimal:
    """Estimated annual lifetime income from a single-premium immediate annuity."""
    income = premium * payout_rate(age)
    return income.quantize(CENT, rounding=ROUND_HALF_UP)
