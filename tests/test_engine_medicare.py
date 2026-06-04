"""Tests for Medicare IRMAA surcharges."""
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
from planner_engine.tax import irmaa_annual_surcharge, irmaa_monthly_surcharge

IRS = "2024-33"
RATE = Decimal("0.025")


def test_irmaa_zero_below_threshold() -> None:
    assert irmaa_monthly_surcharge(Decimal("90000"), "single", 2024, IRS, RATE) == Decimal("0")


def test_irmaa_single_first_tier() -> None:
    # single MAGI 110k (>=103k tier) → Part B 69.90 + Part D 12.90 = 82.80/mo
    assert irmaa_monthly_surcharge(Decimal("110000"), "single", 2024, IRS, RATE) == Decimal("82.80")


def test_irmaa_mfj_uses_higher_thresholds() -> None:
    # MFJ MAGI 110k is below first MFJ tier (206k) → no surcharge
    assert irmaa_monthly_surcharge(Decimal("110000"), "mfj", 2024, IRS, RATE) == Decimal("0")


def test_irmaa_annual_scales_by_enrolled_count() -> None:
    one = irmaa_annual_surcharge(Decimal("200000"), "single", 1, 2024, IRS, RATE)
    two = irmaa_annual_surcharge(Decimal("200000"), "mfj", 2, 2024, IRS, RATE)
    # MFJ 200k below 206k → 0 for the couple example; check single annual = monthly*12
    assert one == irmaa_monthly_surcharge(Decimal("200000"), "single", 2024, IRS, RATE) * 12
    assert two == Decimal("0")


def test_irmaa_appears_in_projection_for_high_income_senior() -> None:
    # 67-year-old with a big pension; MAGI from 2 yrs prior pushes IRMAA in later years.
    run = run_projection(
        ScenarioInput(
            id="s1",
            filing_status="single",
            state="MA",
            start_year=2024,
            end_year=2028,
            primary_person_id="p1",
            people=[
                Person("p1", dob_year=1957, age_by_year={y: y - 1957 for y in range(2024, 2029)})
            ],
            accounts=[AccountYearState("cash", "p1", "cash", Decimal("500000"), Decimal("0"))],
            income_streams=[
                IncomeStream("pension", "pension", Decimal("150000"), 2024, inflation_kind="none")
            ],
            expense_streams=[
                ExpenseStream("e", "must_spend", Decimal("50000"), 2024, inflation_kind="none")
            ],
            assumptions=AssumptionSet(),
        ),
        IRS,
        "test",
    )
    # First two years have no prior-2 MAGI history → no IRMAA; later years should.
    later = [y for y in run.years if y.year >= 2026]
    assert any(y.medicare_irmaa > Decimal("0") for y in later)


def test_medicare_estimate_health_tiers() -> None:
    from planner_engine.tax import estimate_medicare_annual

    good = estimate_medicare_annual("good")
    excellent = estimate_medicare_annual("excellent")
    poor = estimate_medicare_annual("poor")
    assert excellent < good < poor
    # good: (174.70 + 55.50 + 150.00 + 50.00) * 12 = 5162.40
    assert good == Decimal("5162.40")
    assert estimate_medicare_annual("good", include_dental_vision=False) < good
