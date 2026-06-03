from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

from irs_data import Bracket, get_federal_brackets, get_standard_deduction, load_table

CENT = Decimal("0.01")
ZERO = Decimal("0")
HALF = Decimal("0.5")
SS_MAX_TAXABLE_RATE = Decimal("0.85")
SS_TIER_ONE_RATE = Decimal("0.50")
EARLY_WITHDRAWAL_PENALTY_RATE = Decimal("0.10")
HSA_EARLY_PENALTY_RATE = Decimal("0.20")
MA_DEFAULT_VERSION = "2024-33"


@dataclass(frozen=True)
class TaxInput:
    year: int
    filing_status: str
    state: str
    ages: dict[str, int]
    wages: Decimal = ZERO
    wages_state: Decimal | None = None
    pensions_taxable_federal: Decimal = ZERO
    pensions_taxable_state: Decimal = ZERO
    traditional_distributions: Decimal = ZERO
    roth_conversions: Decimal = ZERO
    sepp_distributions: Decimal = ZERO
    rmd_distributions: Decimal = ZERO
    annuity_taxable: Decimal = ZERO
    ltcg: Decimal = ZERO
    ss_gross: Decimal = ZERO
    penalty_eligible_distributions: Decimal = ZERO
    hsa_penalty_eligible_distributions: Decimal = ZERO
    tax_exempt_interest: Decimal = ZERO
    irs_data_version: str = MA_DEFAULT_VERSION


@dataclass(frozen=True)
class TaxableIncomeMA:
    wages: Decimal = ZERO
    pensions_taxable_state: Decimal = ZERO
    traditional_distributions: Decimal = ZERO
    roth_conversions: Decimal = ZERO
    sepp_distributions: Decimal = ZERO
    rmd_distributions: Decimal = ZERO
    annuity_taxable: Decimal = ZERO
    ltcg: Decimal = ZERO


@dataclass(frozen=True)
class TaxResult:
    federal_tax: Decimal
    state_tax: Decimal
    early_withdrawal_penalty: Decimal
    hsa_penalty: Decimal
    agi: Decimal
    magi: Decimal
    provisional_income: Decimal
    ss_taxable_portion: Decimal
    ordinary_income: Decimal
    ordinary_taxable: Decimal
    ltcg_tax: Decimal
    federal_ordinary_tax: Decimal
    audit: dict[str, Any]


def quantize_cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def positive(value: Decimal) -> Decimal:
    return max(ZERO, value)


def ordinary_income_excluding_social_security(inp: TaxInput) -> Decimal:
    return (
        inp.wages
        + inp.pensions_taxable_federal
        + inp.traditional_distributions
        + inp.roth_conversions
        + inp.sepp_distributions
        + inp.rmd_distributions
        + inp.annuity_taxable
    )


def compute_provisional_income(
    ordinary_excluding_ss: Decimal,
    ltcg: Decimal,
    ss_gross: Decimal,
) -> Decimal:
    return ordinary_excluding_ss + ltcg + (ss_gross * HALF)


def taxable_social_security(
    provisional_income: Decimal,
    ss_gross: Decimal,
    filing_status: str,
    irs_data_version: str,
) -> Decimal:
    # IRS Social Security thresholds are intentionally not indexed.
    thresholds = cast(
        dict[str, dict[str, Decimal]],
        load_table("ss_taxation_thresholds", irs_data_version),
    )
    status_thresholds = thresholds[filing_status]
    base = status_thresholds["base"]
    adjusted_base = status_thresholds["adjustedBase"]

    if provisional_income <= base:
        taxable = ZERO
    elif provisional_income <= adjusted_base:
        taxable = (provisional_income - base) * SS_TIER_ONE_RATE
    else:
        tier_one_width = adjusted_base - base
        taxable = (tier_one_width * SS_TIER_ONE_RATE) + (
            (provisional_income - adjusted_base) * SS_MAX_TAXABLE_RATE
        )
    return quantize_cents(min(ss_gross * SS_MAX_TAXABLE_RATE, taxable))


def apply_brackets(taxable_income: Decimal, brackets: list[Bracket]) -> Decimal:
    taxable_income = positive(taxable_income)
    tax = ZERO
    for bracket in brackets:
        ceiling = (
            taxable_income
            if bracket.ceiling is None
            else min(taxable_income, bracket.ceiling)
        )
        amount_in_bracket = positive(ceiling - bracket.floor)
        if amount_in_bracket > ZERO:
            tax += amount_in_bracket * bracket.rate
        if bracket.ceiling is not None and taxable_income <= bracket.ceiling:
            break
    return quantize_cents(tax)


def apply_ordinary_brackets(
    ordinary_taxable: Decimal,
    year: int,
    filing_status: str,
    irs_data_version: str,
) -> Decimal:
    return apply_brackets(
        ordinary_taxable,
        get_federal_brackets(year, filing_status, irs_data_version),
    )


def get_ltcg_brackets(year: int, filing_status: str, irs_data_version: str) -> list[Bracket]:
    table = cast(
        dict[str, dict[str, list[dict[str, Decimal | None]]]],
        load_table("ltcg_brackets", irs_data_version),
    )
    source_year = max(int(candidate) for candidate in table if int(candidate) <= year)
    rows = table[str(source_year)][filing_status]
    return [
        Bracket(
            rate=_required_decimal(row["rate"]),
            floor=_required_decimal(row["floor"]),
            ceiling=None if row["ceiling"] is None else _required_decimal(row["ceiling"]),
        )
        for row in rows
    ]


def _required_decimal(value: Decimal | None) -> Decimal:
    if value is None:
        raise ValueError("Expected Decimal value, got None")
    return value


def apply_ltcg_brackets_stacked(
    ordinary_taxable: Decimal,
    ltcg: Decimal,
    year: int,
    filing_status: str,
    irs_data_version: str,
) -> Decimal:
    remaining = positive(ltcg)
    ordinary_floor = positive(ordinary_taxable)
    tax = ZERO
    for bracket in get_ltcg_brackets(year, filing_status, irs_data_version):
        if remaining <= ZERO:
            break
        bracket_start = max(ordinary_floor, bracket.floor)
        bracket_end = bracket.ceiling
        if bracket_end is None:
            taxable_at_rate = remaining
        elif bracket_end <= bracket_start:
            taxable_at_rate = ZERO
        else:
            taxable_at_rate = min(remaining, bracket_end - bracket_start)
        tax += taxable_at_rate * bracket.rate
        remaining -= taxable_at_rate
        ordinary_floor += taxable_at_rate
    return quantize_cents(tax)


def federal_tax(
    ordinary_taxable: Decimal,
    ltcg: Decimal,
    year: int,
    filing_status: str,
    irs_data_version: str,
) -> tuple[Decimal, Decimal, Decimal]:
    ordinary_tax = apply_ordinary_brackets(ordinary_taxable, year, filing_status, irs_data_version)
    ltcg_tax = apply_ltcg_brackets_stacked(
        ordinary_taxable,
        ltcg,
        year,
        filing_status,
        irs_data_version,
    )
    return quantize_cents(ordinary_tax + ltcg_tax), ordinary_tax, ltcg_tax


def state_tax_ma(
    taxable_income_components: TaxableIncomeMA,
    year: int,
    irs_data_version: str,
) -> Decimal:
    table = cast(dict[str, dict[str, Any]], load_table("ma_state", irs_data_version))
    source_year = max(int(candidate) for candidate in table if int(candidate) <= year)
    row = table[str(source_year)]
    flat_rate = cast(Decimal, row["flatRate"])
    surtax_rate = cast(Decimal, row["surtaxRate"])
    surtax_threshold = cast(Decimal, row["surtaxThreshold"])
    taxable_income = (
        taxable_income_components.wages
        + taxable_income_components.pensions_taxable_state
        + taxable_income_components.traditional_distributions
        + taxable_income_components.roth_conversions
        + taxable_income_components.sepp_distributions
        + taxable_income_components.rmd_distributions
        + taxable_income_components.annuity_taxable
        + taxable_income_components.ltcg
    )
    flat_tax = positive(taxable_income) * flat_rate
    surtax = positive(taxable_income - surtax_threshold) * surtax_rate
    return quantize_cents(flat_tax + surtax)


def compute_early_withdrawal_penalty(
    penalty_eligible_distributions: Decimal,
    hsa_penalty_eligible_distributions: Decimal = ZERO,
) -> tuple[Decimal, Decimal]:
    early_penalty = quantize_cents(
        positive(penalty_eligible_distributions) * EARLY_WITHDRAWAL_PENALTY_RATE
    )
    hsa_penalty = quantize_cents(
        positive(hsa_penalty_eligible_distributions) * HSA_EARLY_PENALTY_RATE
    )
    return early_penalty, hsa_penalty


def compute_taxes(inp: TaxInput) -> TaxResult:
    if inp.state != "MA":
        raise ValueError("Only Massachusetts state tax is supported in MVP")

    ordinary_excluding_ss = ordinary_income_excluding_social_security(inp)
    provisional_income = compute_provisional_income(ordinary_excluding_ss, inp.ltcg, inp.ss_gross)
    ss_taxable = taxable_social_security(
        provisional_income,
        inp.ss_gross,
        inp.filing_status,
        inp.irs_data_version,
    )
    ordinary_income = ordinary_excluding_ss + ss_taxable
    agi = ordinary_income + inp.ltcg
    non_taxable_ss = inp.ss_gross - ss_taxable
    magi = agi + inp.tax_exempt_interest + non_taxable_ss
    standard_deduction = get_standard_deduction(inp.year, inp.filing_status, inp.irs_data_version)
    total_taxable_income = positive(agi - standard_deduction)
    ordinary_taxable = positive(ordinary_income - standard_deduction)
    ltcg_taxable = min(inp.ltcg, positive(total_taxable_income - ordinary_taxable))
    total_federal, ordinary_tax, ltcg_tax = federal_tax(
        ordinary_taxable,
        ltcg_taxable,
        inp.year,
        inp.filing_status,
        inp.irs_data_version,
    )
    state_tax = state_tax_ma(
        TaxableIncomeMA(
            wages=inp.wages if inp.wages_state is None else inp.wages_state,
            pensions_taxable_state=inp.pensions_taxable_state,
            traditional_distributions=inp.traditional_distributions,
            roth_conversions=inp.roth_conversions,
            sepp_distributions=inp.sepp_distributions,
            rmd_distributions=inp.rmd_distributions,
            annuity_taxable=inp.annuity_taxable,
            ltcg=inp.ltcg,
        ),
        inp.year,
        inp.irs_data_version,
    )
    early_penalty, hsa_penalty = compute_early_withdrawal_penalty(
        inp.penalty_eligible_distributions,
        inp.hsa_penalty_eligible_distributions,
    )

    return TaxResult(
        federal_tax=total_federal,
        state_tax=state_tax,
        early_withdrawal_penalty=early_penalty,
        hsa_penalty=hsa_penalty,
        agi=quantize_cents(agi),
        magi=quantize_cents(magi),
        provisional_income=quantize_cents(provisional_income),
        ss_taxable_portion=ss_taxable,
        ordinary_income=quantize_cents(ordinary_income),
        ordinary_taxable=quantize_cents(ordinary_taxable),
        ltcg_tax=ltcg_tax,
        federal_ordinary_tax=ordinary_tax,
        audit={
            "ordinary_excluding_ss": str(ordinary_excluding_ss),
            "standard_deduction": str(standard_deduction),
            "total_taxable_income": str(total_taxable_income),
            "ltcg_taxable": str(ltcg_taxable),
            "non_taxable_ss": str(non_taxable_ss),
        },
    )
