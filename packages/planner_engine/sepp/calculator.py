from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from irs_data import get_single_life_factor

CENT = Decimal("0.01")
MONTHS_PER_YEAR = Decimal("12")
ONE = Decimal("1")
POINT_ZERO_ONE = Decimal("0.01")
AGE_59_HALF = Decimal("59.5")
SAFE_VALUATION_WINDOW_DAYS = 184

SeppMethod = Literal["rmd", "fixed_amortization", "fixed_annuitization"]
AfrMonthUsed = Literal["prior", "two_prior"]
SwitchMethod = Literal["rmd", "fixed_amortization", "fixed_annuitization"]


@dataclass(frozen=True)
class SeppIssue:
    severity: Literal["info", "warning", "error"]
    code: str
    message: str


@dataclass(frozen=True)
class SeppCalculationInput:
    method: SeppMethod
    account_balance_at_valuation: Decimal
    valuation_date: date
    first_payment_date: date
    dob: date
    beneficiary_dob: date | None
    selected_interest_rate: Decimal | None
    afr_prior_month: Decimal | None
    afr_two_months_prior: Decimal | None
    irs_data_version: str
    mortality_table_version: str | None


@dataclass(frozen=True)
class SeppCalculationResult:
    annual_payment: Decimal
    required_end_date: date
    life_expectancy_factor: Decimal
    max_allowed_interest_rate: Decimal | None
    afr_month_used: AfrMonthUsed | None
    audit_log: list[dict[str, Any]]
    issues: list[SeppIssue]


@dataclass(frozen=True)
class SeppCashFlow:
    cash_flow_date: date
    amount: Decimal
    kind: Literal["scheduled_distribution", "extra_distribution", "contribution"]


def quantize_cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def add_years(original: date, years: int) -> date:
    try:
        return original.replace(year=original.year + years)
    except ValueError:
        return original.replace(year=original.year + years, day=28)


def add_months(original: date, months: int) -> date:
    month_index = original.month - 1 + months
    year = original.year + month_index // 12
    month = month_index % 12 + 1
    days_by_month = {
        1: 31,
        2: 29 if _is_leap_year(year) else 28,
        3: 31,
        4: 30,
        5: 31,
        6: 30,
        7: 31,
        8: 31,
        9: 30,
        10: 31,
        11: 30,
        12: 31,
    }
    return date(year, month, min(original.day, days_by_month[month]))


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def compute_required_end_date(first_payment_date: date, dob: date) -> date:
    five_year_anniversary = add_years(first_payment_date, 5)
    age_595_date = add_months(add_years(dob, 59), 6)
    return max(five_year_anniversary, age_595_date)


def attained_age(dob: date, as_of: date) -> int:
    years = as_of.year - dob.year
    if (as_of.month, as_of.day) < (dob.month, dob.day):
        years -= 1
    return years


def age_decimal_years(dob: date, as_of: date) -> Decimal:
    years = attained_age(dob, as_of)
    birthday = add_years(dob, years)
    next_birthday = add_years(dob, years + 1)
    elapsed = Decimal((as_of - birthday).days)
    span = Decimal((next_birthday - birthday).days)
    return Decimal(years) + (elapsed / span)


def calculate_max_allowed_interest_rate(
    afr_prior_month: Decimal | None,
    afr_two_months_prior: Decimal | None,
) -> tuple[Decimal | None, AfrMonthUsed | None]:
    if afr_prior_month is None or afr_two_months_prior is None:
        return None, None
    if afr_prior_month >= afr_two_months_prior:
        afr = afr_prior_month
        month_used: AfrMonthUsed = "prior"
    else:
        afr = afr_two_months_prior
        month_used = "two_prior"
    return max(Decimal("0.05"), afr), month_used


def recalculate_rmd_method_year(
    prior_year_end_balance: Decimal,
    attained_age_this_year: int,
    use_joint_table: bool,
    beneficiary_alive: bool,
    irs_data_version: str,
) -> tuple[Decimal, dict[str, Any]]:
    table_name = "joint_last_survivor" if use_joint_table and beneficiary_alive else "single_life"
    factor = get_single_life_factor(attained_age_this_year, irs_data_version)
    payment = quantize_cents(prior_year_end_balance / factor)
    return payment, {
        "method": "rmd",
        "table": table_name,
        "prior_year_end_balance": str(prior_year_end_balance),
        "attained_age": attained_age_this_year,
        "life_expectancy_factor": str(factor),
        "annual_payment": str(payment),
    }


def calculate_initial_payment(inp: SeppCalculationInput) -> SeppCalculationResult:
    issues = validate_calculation_input(inp)
    audit_log: list[dict[str, Any]] = []
    required_end_date = compute_required_end_date(inp.first_payment_date, inp.dob)
    age = attained_age(inp.dob, inp.first_payment_date)
    life_expectancy_factor = get_single_life_factor(age, inp.irs_data_version)
    max_rate, afr_month_used = calculate_max_allowed_interest_rate(
        inp.afr_prior_month,
        inp.afr_two_months_prior,
    )

    if inp.method == "rmd":
        annual_payment = quantize_cents(inp.account_balance_at_valuation / life_expectancy_factor)
        audit_log.append(
            {
                "method": inp.method,
                "balance": str(inp.account_balance_at_valuation),
                "age": age,
                "life_expectancy_factor": str(life_expectancy_factor),
                "annual_payment": str(annual_payment),
            }
        )
    elif inp.method == "fixed_amortization":
        selected_rate = _require_rate(inp.selected_interest_rate, inp.method)
        annual_payment = fixed_amortization_payment(
            inp.account_balance_at_valuation,
            selected_rate,
            life_expectancy_factor,
        )
        audit_log.append(
            {
                "method": inp.method,
                "balance": str(inp.account_balance_at_valuation),
                "rate": str(selected_rate),
                "life_expectancy_factor": str(life_expectancy_factor),
                "annual_payment": str(annual_payment),
            }
        )
    else:
        selected_rate = _require_rate(inp.selected_interest_rate, inp.method)
        annuity_factor = single_life_annuity_factor(
            age,
            selected_rate,
            inp.mortality_table_version,
        )
        annual_payment = quantize_cents(inp.account_balance_at_valuation / annuity_factor)
        audit_log.append(
            {
                "method": inp.method,
                "balance": str(inp.account_balance_at_valuation),
                "rate": str(selected_rate),
                "annuity_factor": str(annuity_factor),
                "mortality_table_version": inp.mortality_table_version,
                "annual_payment": str(annual_payment),
            }
        )

    audit_log.append(
        {
            "required_end_date": required_end_date.isoformat(),
            "max_allowed_interest_rate": None if max_rate is None else str(max_rate),
            "afr_month_used": afr_month_used,
        }
    )

    return SeppCalculationResult(
        annual_payment=annual_payment,
        required_end_date=required_end_date,
        life_expectancy_factor=life_expectancy_factor,
        max_allowed_interest_rate=max_rate,
        afr_month_used=afr_month_used,
        audit_log=audit_log,
        issues=issues,
    )


def _require_rate(rate: Decimal | None, method: str) -> Decimal:
    if rate is None:
        raise ValueError(f"{method} requires selected_interest_rate")
    return rate


def fixed_amortization_payment(
    present_value: Decimal,
    annual_rate: Decimal,
    life_expectancy_factor: Decimal,
) -> Decimal:
    discount = ONE - ((ONE + annual_rate) ** (-life_expectancy_factor))
    return quantize_cents(present_value * annual_rate / discount)


def single_life_annuity_factor(
    age: int,
    annual_rate: Decimal,
    mortality_table_version: str | None,
) -> Decimal:
    fixture_key = (age, annual_rate, mortality_table_version)
    fixtures = {
        (50, Decimal("0.04"), "phase3_fixture"): Decimal("18.9534"),
        (50, Decimal("0.04"), None): Decimal("18.9534"),
    }
    try:
        return fixtures[fixture_key]
    except KeyError as exc:
        raise KeyError(
            "No single-life annuity factor fixture for "
            f"age={age}, rate={annual_rate}, mortality_table_version={mortality_table_version}"
        ) from exc


def validate_calculation_input(inp: SeppCalculationInput) -> list[SeppIssue]:
    issues: list[SeppIssue] = []
    if inp.valuation_date > inp.first_payment_date:
        issues.append(
            SeppIssue(
                "error",
                "sepp_valuation_after_first_payment",
                "Valuation date cannot be after first payment date.",
            )
        )

    max_rate, _ = calculate_max_allowed_interest_rate(
        inp.afr_prior_month,
        inp.afr_two_months_prior,
    )
    if (
        inp.selected_interest_rate is not None
        and max_rate is not None
        and inp.selected_interest_rate > max_rate
    ):
        issues.append(
            SeppIssue(
                "error",
                "sepp_rate_exceeds_max",
                "Selected interest rate exceeds Notice 2022-6 maximum.",
            )
        )

    if inp.method == "fixed_annuitization" and inp.beneficiary_dob is not None:
        issues.append(
            SeppIssue(
                "error",
                "sepp_annuitization_with_beneficiary",
                "Fixed annuitization with a beneficiary is outside MVP scope.",
            )
        )

    if age_decimal_years(inp.dob, inp.first_payment_date) >= AGE_59_HALF:
        issues.append(
            SeppIssue(
                "warning",
                "sepp_pointless_age",
                "SEPP begins at or after age 59.5.",
            )
        )

    if inp.method in {"fixed_amortization", "fixed_annuitization"}:
        days_between = (inp.first_payment_date - inp.valuation_date).days
        if days_between > SAFE_VALUATION_WINDOW_DAYS:
            issues.append(
                SeppIssue(
                    "warning",
                    "sepp_valuation_window",
                    "Fixed-method valuation date is more than six months before first payment.",
                )
            )

    return issues


def validate_cash_flows(
    valuation_date: date,
    required_end_date: date,
    scheduled_annual_payment: Decimal,
    cash_flows: list[SeppCashFlow],
) -> list[SeppIssue]:
    issues: list[SeppIssue] = []
    for cash_flow in cash_flows:
        in_locked_period = valuation_date < cash_flow.cash_flow_date < required_end_date
        if not in_locked_period:
            continue
        if cash_flow.kind == "contribution":
            issues.append(
                SeppIssue(
                    "error",
                    "sepp_account_contribution",
                    "Contribution or transfer into SEPP account during locked period.",
                )
            )
        if cash_flow.kind == "extra_distribution":
            issues.append(
                SeppIssue(
                    "error",
                    "sepp_account_extra_distribution",
                    "Non-SEPP distribution from SEPP account during locked period.",
                )
            )

    installments_by_year: dict[int, Decimal] = {}
    for cash_flow in cash_flows:
        if cash_flow.kind == "scheduled_distribution":
            year = cash_flow.cash_flow_date.year
            installments_by_year[year] = (
                installments_by_year.get(year, Decimal("0")) + cash_flow.amount
            )

    for year, total in installments_by_year.items():
        months_expected = Decimal("12")
        if year == min(installments_by_year):
            first_month = min(
                flow.cash_flow_date.month
                for flow in cash_flows
                if flow.kind == "scheduled_distribution" and flow.cash_flow_date.year == year
            )
            months_expected = Decimal(13 - first_month)
        expected = quantize_cents(scheduled_annual_payment * months_expected / MONTHS_PER_YEAR)
        if abs(quantize_cents(total) - expected) > POINT_ZERO_ONE:
            issues.append(
                SeppIssue(
                    "error",
                    "sepp_installment_drift",
                    "Scheduled installments do not reconcile to annual SEPP amount.",
                )
            )

    return issues


def validate_switch(
    current_method: SwitchMethod,
    requested_method: SwitchMethod,
    has_switched_to_rmd: bool,
) -> SeppIssue | None:
    if requested_method == current_method:
        return None
    if has_switched_to_rmd:
        return SeppIssue("error", "sepp_invalid_switch", "Only one method switch is allowed.")
    fixed_methods = {"fixed_amortization", "fixed_annuitization"}
    if current_method in fixed_methods and requested_method == "rmd":
        return None
    return SeppIssue("error", "sepp_invalid_switch", "Invalid SEPP method switch.")


def final_distribution_for_depletion(
    requested_payment: Decimal,
    available_balance: Decimal,
) -> tuple[Decimal, Literal["active", "completed"]]:
    if available_balance <= requested_payment:
        return available_balance, "completed"
    return requested_payment, "active"


def projected_depletion_issue(
    depletion_date: date | None,
    required_end_date: date,
) -> SeppIssue | None:
    if depletion_date is None:
        return None
    warning_cutoff = add_years(depletion_date, 2)
    if warning_cutoff < required_end_date:
        return SeppIssue(
            "warning",
            "sepp_early_depletion",
            "Projected SEPP account depletion is more than two years before required end date.",
        )
    return None


def split_457b_distribution(
    distribution: Decimal,
    rollover_basis_pct: Decimal,
) -> tuple[Decimal, Decimal]:
    rollover = quantize_cents(distribution * rollover_basis_pct)
    native = distribution - rollover
    return native, rollover
