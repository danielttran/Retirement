"""Tests for the Social Security claiming-age explorer."""
from __future__ import annotations

from decimal import Decimal

from planner_engine.socialsecurity import (
    benefit_multiplier,
    explore_claiming_ages,
    full_retirement_age_months,
    pia_from_benefit,
)


def test_fra_by_birth_year() -> None:
    assert full_retirement_age_months(1960) == 67 * 12
    assert full_retirement_age_months(1955) == 66 * 12 + 2
    assert full_retirement_age_months(1950) == 66 * 12


def test_multiplier_at_fra_is_one() -> None:
    assert benefit_multiplier(67 * 12, 67 * 12) == Decimal("1")


def test_multiplier_early_claim_62() -> None:
    # FRA 67, claim at 62 (60 months early): 36*5/900 + 24*5/1200 = 0.20 + 0.10 = 0.30 → 0.70
    assert benefit_multiplier(62 * 12, 67 * 12) == Decimal("0.70")


def test_multiplier_delayed_to_70() -> None:
    # FRA 67, claim at 70 (36 months late): 36 * 8/1200 = 0.24 → 1.24
    assert benefit_multiplier(70 * 12, 67 * 12) == Decimal("1.24")


def test_pia_roundtrips() -> None:
    pia = pia_from_benefit(Decimal("21000"), 62, 67 * 12)  # 21000 = 0.70 * PIA → 30000
    assert pia == Decimal("30000")


def test_explorer_shapes_and_max_lifetime() -> None:
    result = explore_claiming_ages(
        pia_annual=Decimal("30000"),
        birth_year=1965,
        life_expectancy_age=90,
        cola_rate=Decimal("0.02"),
    )
    assert len(result.options) == 9  # ages 62..70
    by_age = {o.claiming_age: o for o in result.options}
    assert by_age[62].annual_benefit == Decimal("21000.00")
    assert by_age[70].annual_benefit == Decimal("37200.00")
    # With a long life expectancy, delaying maximizes lifetime benefit.
    assert result.max_lifetime_claiming_age == 70
    # Delaying to 70 should have a break-even age in the late 70s / early 80s.
    assert by_age[70].break_even_age_vs_earliest is not None


def test_short_life_expectancy_favors_early_claim() -> None:
    result = explore_claiming_ages(
        pia_annual=Decimal("30000"),
        birth_year=1965,
        life_expectancy_age=70,
        cola_rate=Decimal("0"),
    )
    assert result.max_lifetime_claiming_age == 62
