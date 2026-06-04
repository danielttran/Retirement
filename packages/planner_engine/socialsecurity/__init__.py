"""Social Security claiming-age explorer (Boldin-style).

Pure Decimal functions. Given a benefit at a known claiming age (or PIA at Full Retirement Age),
derive the benefit at every claiming age 62-70 using the SSA reduction / delayed-credit rules, and
compare cumulative lifetime benefits + break-even ages against longevity.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0")
ONE = Decimal("1")
TWELVE = Decimal("12")
# Early-claim reduction: 5/9 of 1% per month for the first 36 months, 5/12 of 1% beyond.
_EARLY_FIRST36_PER_MONTH = Decimal("5") / Decimal("900")
_EARLY_BEYOND_PER_MONTH = Decimal("5") / Decimal("1200")
# Delayed retirement credit: 8% per year = 8/1200 per month, to age 70.
_DELAY_PER_MONTH = Decimal("8") / Decimal("1200")
MIN_CLAIM_AGE = 62
MAX_CLAIM_AGE = 70


@dataclass(frozen=True)
class ClaimingOption:
    claiming_age: int
    monthly_benefit: Decimal
    annual_benefit: Decimal
    lifetime_total: Decimal
    break_even_age_vs_earliest: int | None


@dataclass(frozen=True)
class SocialSecurityExplorerResult:
    pia_annual: Decimal
    full_retirement_age_months: int
    options: list[ClaimingOption]
    max_lifetime_claiming_age: int


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def full_retirement_age_months(birth_year: int) -> int:
    """SSA Full Retirement Age in months by birth year."""
    if birth_year <= 1937:
        return 65 * 12
    if 1938 <= birth_year <= 1942:
        return 65 * 12 + (birth_year - 1937) * 2
    if 1943 <= birth_year <= 1954:
        return 66 * 12
    if 1955 <= birth_year <= 1959:
        return 66 * 12 + (birth_year - 1954) * 2
    return 67 * 12


def benefit_multiplier(claiming_age_months: int, fra_months: int) -> Decimal:
    """Benefit as a fraction of PIA when claimed at ``claiming_age_months``."""
    diff = claiming_age_months - fra_months
    if diff == 0:
        return ONE
    if diff < 0:
        early = -diff
        first36 = min(early, 36)
        beyond = max(0, early - 36)
        reduction = Decimal(first36) * _EARLY_FIRST36_PER_MONTH + (
            Decimal(beyond) * _EARLY_BEYOND_PER_MONTH
        )
        return ONE - reduction
    return ONE + Decimal(diff) * _DELAY_PER_MONTH


def pia_from_benefit(annual_benefit: Decimal, claiming_age: int, fra_months: int) -> Decimal:
    """Back out PIA (annual, at FRA) from a benefit known at a given claiming age."""
    multiplier = benefit_multiplier(claiming_age * 12, fra_months)
    if multiplier == ZERO:
        return ZERO
    return annual_benefit / multiplier


def _lifetime_total(
    annual_at_claim: Decimal,
    claiming_age: int,
    life_expectancy_age: int,
    cola_rate: Decimal,
) -> Decimal:
    total = ZERO
    benefit = annual_at_claim
    for _age in range(claiming_age, life_expectancy_age + 1):
        total += benefit
        benefit = benefit * (ONE + cola_rate)
    return total


def explore_claiming_ages(
    pia_annual: Decimal,
    birth_year: int,
    life_expectancy_age: int,
    cola_rate: Decimal,
) -> SocialSecurityExplorerResult:
    fra_months = full_retirement_age_months(birth_year)
    raw: list[tuple[int, Decimal, Decimal, Decimal]] = []
    for age in range(MIN_CLAIM_AGE, MAX_CLAIM_AGE + 1):
        annual = _quantize(pia_annual * benefit_multiplier(age * 12, fra_months))
        monthly = _quantize(annual / TWELVE)
        lifetime = _quantize(_lifetime_total(annual, age, life_expectancy_age, cola_rate))
        raw.append((age, monthly, annual, lifetime))

    earliest_annual = raw[0][2]
    options: list[ClaimingOption] = []
    for age, monthly, annual, lifetime in raw:
        break_even = _break_even_age(
            earliest_annual, MIN_CLAIM_AGE, annual, age, life_expectancy_age, cola_rate
        )
        options.append(
            ClaimingOption(
                claiming_age=age,
                monthly_benefit=monthly,
                annual_benefit=annual,
                lifetime_total=lifetime,
                break_even_age_vs_earliest=break_even,
            )
        )
    best = max(raw, key=lambda row: row[3])
    return SocialSecurityExplorerResult(
        pia_annual=_quantize(pia_annual),
        full_retirement_age_months=fra_months,
        options=options,
        max_lifetime_claiming_age=best[0],
    )


def _break_even_age(
    early_annual: Decimal,
    early_age: int,
    later_annual: Decimal,
    later_age: int,
    life_expectancy_age: int,
    cola_rate: Decimal,
) -> int | None:
    """First age at which cumulative benefits of the later claim overtake the earlier claim."""
    if later_age == early_age:
        return None
    early_cum = ZERO
    later_cum = ZERO
    early_benefit = early_annual
    later_benefit = later_annual
    for age in range(early_age, life_expectancy_age + 1):
        early_cum += early_benefit
        early_benefit = early_benefit * (ONE + cola_rate)
        if age >= later_age:
            later_cum += later_benefit
            later_benefit = later_benefit * (ONE + cola_rate)
        if age >= later_age and later_cum >= early_cum:
            return age
    return None
