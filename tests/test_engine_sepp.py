from __future__ import annotations

from datetime import date
from decimal import Decimal

from planner_engine.sepp import (
    SeppCalculationInput,
    SeppCashFlow,
    calculate_initial_payment,
    calculate_max_allowed_interest_rate,
    compute_required_end_date,
    final_distribution_for_depletion,
    projected_depletion_issue,
    recalculate_rmd_method_year,
    split_457b_distribution,
    validate_cash_flows,
    validate_switch,
)


def base_input(method: str) -> SeppCalculationInput:
    return SeppCalculationInput(
        method=method,  # type: ignore[arg-type]
        account_balance_at_valuation=Decimal("400000"),
        valuation_date=date(2024, 12, 31),
        first_payment_date=date(2025, 1, 15),
        dob=date(1975, 1, 15),
        beneficiary_dob=None,
        selected_interest_rate=Decimal("0.04"),
        afr_prior_month=Decimal("0.048"),
        afr_two_months_prior=Decimal("0.049"),
        irs_data_version="2024-33",
        mortality_table_version="phase3_fixture",
    )


def issue_codes(result_or_issues: object) -> set[str]:
    issues = getattr(result_or_issues, "issues", result_or_issues)
    return {issue.code for issue in issues}  # type: ignore[union-attr]


def test_01_rmd_method_year_one_payment() -> None:
    result = calculate_initial_payment(base_input("rmd"))
    assert result.annual_payment == Decimal("11049.72")
    assert result.life_expectancy_factor == Decimal("36.2")


def test_02_fixed_amortization_payment_locks_to_cent() -> None:
    result = calculate_initial_payment(base_input("fixed_amortization"))
    assert result.annual_payment == Decimal("21101.63")


def test_03_fixed_annuitization_uses_locked_single_life_fixture() -> None:
    result = calculate_initial_payment(base_input("fixed_annuitization"))
    assert result.annual_payment == Decimal("21104.39")
    assert result.audit_log[0]["annuity_factor"] == "18.9534"


def test_04_required_end_date_age_56_start_uses_five_year_rule() -> None:
    assert compute_required_end_date(date(2025, 1, 15), date(1969, 1, 15)) == date(2030, 1, 15)


def test_05_required_end_date_age_50_start_uses_age_59_and_half() -> None:
    assert compute_required_end_date(date(2025, 1, 15), date(1975, 7, 15)) == date(2035, 1, 15)


def test_06_extra_non_sepp_withdrawal_before_required_end_date_errors() -> None:
    issues = validate_cash_flows(
        date(2024, 12, 31),
        date(2030, 1, 15),
        Decimal("12000"),
        [SeppCashFlow(date(2026, 3, 1), Decimal("1000"), "extra_distribution")],
    )
    assert "sepp_account_extra_distribution" in issue_codes(issues)


def test_07_contribution_after_valuation_before_required_end_date_errors() -> None:
    issues = validate_cash_flows(
        date(2024, 12, 31),
        date(2030, 1, 15),
        Decimal("12000"),
        [SeppCashFlow(date(2026, 3, 1), Decimal("1000"), "contribution")],
    )
    assert "sepp_account_contribution" in issue_codes(issues)


def test_08_one_time_switch_fixed_amortization_to_rmd_allowed() -> None:
    assert validate_switch("fixed_amortization", "rmd", has_switched_to_rmd=False) is None


def test_09_invalid_switch_rmd_to_fixed_errors() -> None:
    issue = validate_switch("rmd", "fixed_amortization", has_switched_to_rmd=False)
    assert issue is not None
    assert issue.code == "sepp_invalid_switch"


def test_10_complete_depletion_allows_final_short_payment() -> None:
    payment, status = final_distribution_for_depletion(Decimal("12000"), Decimal("7500"))
    assert payment == Decimal("7500")
    assert status == "completed"


def test_11_governmental_457b_rollover_basis_split() -> None:
    native, rollover = split_457b_distribution(Decimal("10000"), Decimal("0.30"))
    assert native == Decimal("7000.00")
    assert rollover == Decimal("3000.00")
    assert rollover * Decimal("0.10") == Decimal("300.0000")


def test_12_rmd_joint_table_switches_to_single_when_beneficiary_dies() -> None:
    payment, audit = recalculate_rmd_method_year(
        Decimal("400000"),
        50,
        use_joint_table=True,
        beneficiary_alive=False,
        irs_data_version="2024-33",
    )
    assert payment == Decimal("11049.72")
    assert audit["table"] == "single_life"


def test_13_monthly_installments_starting_august_reconcile_to_prorated_amount() -> None:
    issues = validate_cash_flows(
        date(2025, 7, 1),
        date(2030, 8, 1),
        Decimal("12000"),
        [
            SeppCashFlow(date(2025, month, 15), Decimal("1000"), "scheduled_distribution")
            for month in range(8, 13)
        ],
    )
    assert "sepp_installment_drift" not in issue_codes(issues)


def test_14_sepp_at_age_60_warns_but_calculates() -> None:
    inp = SeppCalculationInput(
        **{**base_input("rmd").__dict__, "dob": date(1965, 1, 15)}
    )
    result = calculate_initial_payment(inp)
    assert result.annual_payment > Decimal("0")
    assert "sepp_pointless_age" in issue_codes(result)


def test_15_selected_rate_above_max_errors() -> None:
    inp = SeppCalculationInput(
        **{
            **base_input("fixed_amortization").__dict__,
            "selected_interest_rate": Decimal("0.055"),
            "afr_prior_month": Decimal("0.048"),
            "afr_two_months_prior": Decimal("0.052"),
        }
    )
    result = calculate_initial_payment(inp)
    assert result.max_allowed_interest_rate == Decimal("0.052")
    assert "sepp_rate_exceeds_max" in issue_codes(result)


def test_16_selected_rate_at_five_percent_floor_ok() -> None:
    inp = SeppCalculationInput(
        **{
            **base_input("fixed_amortization").__dict__,
            "selected_interest_rate": Decimal("0.050"),
            "afr_prior_month": Decimal("0.048"),
            "afr_two_months_prior": Decimal("0.049"),
        }
    )
    result = calculate_initial_payment(inp)
    assert result.max_allowed_interest_rate == Decimal("0.05")
    assert "sepp_rate_exceeds_max" not in issue_codes(result)


def test_projected_depletion_more_than_two_years_before_required_end_warns() -> None:
    issue = projected_depletion_issue(date(2027, 1, 1), date(2030, 1, 15))
    assert issue is not None
    assert issue.code == "sepp_early_depletion"


def test_leap_day_date_math_and_before_birthday_age_path() -> None:
    assert compute_required_end_date(date(2025, 2, 28), date(1965, 2, 28)) == date(2030, 2, 28)
    assert compute_required_end_date(date(2025, 1, 1), date(1964, 2, 29)) == date(2030, 1, 1)
    result = calculate_initial_payment(
        SeppCalculationInput(
            **{
                **base_input("rmd").__dict__,
                "first_payment_date": date(2025, 1, 14),
            }
        )
    )
    assert result.audit_log[0]["age"] == 49


def test_rate_limit_none_and_prior_month_paths() -> None:
    assert calculate_max_allowed_interest_rate(None, Decimal("0.05")) == (None, None)
    assert calculate_max_allowed_interest_rate(Decimal("0.052"), Decimal("0.049")) == (
        Decimal("0.052"),
        "prior",
    )


def test_missing_rate_for_fixed_method_raises() -> None:
    inp = SeppCalculationInput(
        **{**base_input("fixed_amortization").__dict__, "selected_interest_rate": None}
    )
    try:
        calculate_initial_payment(inp)
    except ValueError as exc:
        assert "fixed_amortization" in str(exc)
    else:
        raise AssertionError("Expected missing fixed-method rate to raise")


def test_missing_annuitization_fixture_raises() -> None:
    inp = SeppCalculationInput(
        **{
            **base_input("fixed_annuitization").__dict__,
            "mortality_table_version": "missing",
        }
    )
    try:
        calculate_initial_payment(inp)
    except KeyError as exc:
        assert "annuity factor fixture" in str(exc)
    else:
        raise AssertionError("Expected missing annuitization fixture to raise")


def test_validation_errors_for_dates_beneficiary_and_old_valuation() -> None:
    inp = SeppCalculationInput(
        **{
            **base_input("fixed_annuitization").__dict__,
            "valuation_date": date(2025, 2, 1),
            "beneficiary_dob": date(1978, 1, 1),
        }
    )
    result = calculate_initial_payment(inp)
    codes = issue_codes(result)
    assert "sepp_valuation_after_first_payment" in codes
    assert "sepp_annuitization_with_beneficiary" in codes

    old_valuation = SeppCalculationInput(
        **{
            **base_input("fixed_amortization").__dict__,
            "valuation_date": date(2024, 1, 1),
        }
    )
    assert "sepp_valuation_window" in issue_codes(calculate_initial_payment(old_valuation))


def test_cash_flows_outside_locked_period_and_drift_branch() -> None:
    issues = validate_cash_flows(
        date(2025, 1, 1),
        date(2030, 1, 1),
        Decimal("12000"),
        [
            SeppCashFlow(date(2024, 12, 1), Decimal("999"), "contribution"),
            SeppCashFlow(date(2025, 8, 15), Decimal("999"), "scheduled_distribution"),
        ],
    )
    codes = issue_codes(issues)
    assert "sepp_account_contribution" not in codes
    assert "sepp_installment_drift" in codes


def test_switch_same_method_second_switch_and_active_depletion_paths() -> None:
    assert validate_switch("rmd", "rmd", has_switched_to_rmd=True) is None
    issue = validate_switch("fixed_annuitization", "rmd", has_switched_to_rmd=True)
    assert issue is not None
    assert issue.code == "sepp_invalid_switch"

    payment, status = final_distribution_for_depletion(Decimal("12000"), Decimal("12500"))
    assert payment == Decimal("12000")
    assert status == "active"


def test_no_projected_depletion_issue_paths() -> None:
    assert projected_depletion_issue(None, date(2030, 1, 1)) is None
    assert projected_depletion_issue(date(2029, 1, 1), date(2030, 1, 1)) is None


# ---------------------------------------------------------------------------
# calculate_initial_payment — formula spot-checks (guards Bug #1's underlying calc).
# ---------------------------------------------------------------------------


def test_fixed_amortization_age_40_balance_297k_rate_5pct() -> None:
    """Verify formula: PV * r / (1 - (1+r)^-n), where age=40 -> n=45.7."""
    inp = SeppCalculationInput(
        method="fixed_amortization",
        account_balance_at_valuation=Decimal("297000"),
        valuation_date=date(2024, 12, 31),
        first_payment_date=date(2025, 1, 15),
        dob=date(1984, 7, 15),  # age 40 at first payment (before birthday)
        beneficiary_dob=None,
        selected_interest_rate=Decimal("0.05"),
        afr_prior_month=Decimal("0.05"),
        afr_two_months_prior=Decimal("0.05"),
        irs_data_version="2024-33",
        mortality_table_version=None,
    )
    result = calculate_initial_payment(inp)
    assert result.life_expectancy_factor == Decimal("45.7")
    # PV * r / (1 - (1+r)^-n) = 297000 * 0.05 / (1 - 1.05^-45.7) ≈ 16639.77
    assert abs(result.annual_payment - Decimal("16639.77")) < Decimal("1.00")
    assert result.annual_payment > Decimal("16000")
    assert result.annual_payment < Decimal("17000")


def test_rmd_method_age_50_balance_100k_uses_factor_36_2() -> None:
    """RMD payment = balance / single_life_factor(50) = 100000 / 36.2."""
    inp = SeppCalculationInput(
        method="rmd",
        account_balance_at_valuation=Decimal("100000"),
        valuation_date=date(2024, 12, 31),
        first_payment_date=date(2025, 1, 15),
        dob=date(1974, 7, 15),  # age 50 at first payment (before birthday)
        beneficiary_dob=None,
        selected_interest_rate=None,
        afr_prior_month=None,
        afr_two_months_prior=None,
        irs_data_version="2024-33",
        mortality_table_version=None,
    )
    result = calculate_initial_payment(inp)
    assert result.life_expectancy_factor == Decimal("36.2")
    expected = (Decimal("100000") / Decimal("36.2")).quantize(Decimal("0.01"))
    assert result.annual_payment == expected
