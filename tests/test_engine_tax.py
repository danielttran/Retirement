from __future__ import annotations

from decimal import Decimal

from irs_data import Bracket
from planner_engine.tax import (
    TaxInput,
    apply_ltcg_brackets_stacked,
    compute_early_withdrawal_penalty,
    compute_provisional_income,
    compute_taxes,
    taxable_social_security,
)
from planner_engine.tax.engine import apply_brackets, ordinary_income_excluding_social_security

BASE = {
    "year": 2024,
    "state": "MA",
    "ages": {"primary": 40},
    "irs_data_version": "2024-33",
}


def assert_tax_result(
    inp: TaxInput,
    federal_tax: str,
    state_tax: str,
    agi: str,
    magi: str,
    ss_taxable: str = "0.00",
    early_penalty: str = "0.00",
    hsa_penalty: str = "0.00",
) -> None:
    result = compute_taxes(inp)
    assert result.federal_tax == Decimal(federal_tax)
    assert result.state_tax == Decimal(state_tax)
    assert result.agi == Decimal(agi)
    assert result.magi == Decimal(magi)
    assert result.ss_taxable_portion == Decimal(ss_taxable)
    assert result.early_withdrawal_penalty == Decimal(early_penalty)
    assert result.hsa_penalty == Decimal(hsa_penalty)


def test_01_zero_income_year_has_no_tax() -> None:
    assert_tax_result(
        TaxInput(filing_status="single", **BASE),
        federal_tax="0.00",
        state_tax="0.00",
        agi="0.00",
        magi="0.00",
    )


def test_02_single_wages_cross_federal_bracket() -> None:
    assert_tax_result(
        TaxInput(filing_status="single", wages=Decimal("50000"), **BASE),
        federal_tax="4016.00",
        state_tax="2500.00",
        agi="50000.00",
        magi="50000.00",
    )


def test_03_mfj_wages_use_mfj_brackets_and_deduction() -> None:
    assert_tax_result(
        TaxInput(filing_status="mfj", wages=Decimal("120000"), **BASE),
        federal_tax="10432.00",
        state_tax="6000.00",
        agi="120000.00",
        magi="120000.00",
    )


def test_04_hoh_wages_use_head_of_household_brackets() -> None:
    assert_tax_result(
        TaxInput(filing_status="hoh", wages=Decimal("80000"), **BASE),
        federal_tax="6641.00",
        state_tax="4000.00",
        agi="80000.00",
        magi="80000.00",
    )


def test_05_social_security_zero_taxable_tier() -> None:
    assert_tax_result(
        TaxInput(filing_status="single", ss_gross=Decimal("20000"), **BASE),
        federal_tax="0.00",
        state_tax="0.00",
        agi="0.00",
        magi="20000.00",
        ss_taxable="0.00",
    )


def test_06_social_security_fifty_percent_tier() -> None:
    assert_tax_result(
        TaxInput(
            filing_status="single",
            wages=Decimal("20000"),
            ss_gross=Decimal("20000"),
            **BASE,
        ),
        federal_tax="790.00",
        state_tax="1000.00",
        agi="22500.00",
        magi="40000.00",
        ss_taxable="2500.00",
    )


def test_07_social_security_eighty_five_percent_cap() -> None:
    assert_tax_result(
        TaxInput(
            filing_status="single",
            wages=Decimal("50000"),
            ss_gross=Decimal("30000"),
            **BASE,
        ),
        federal_tax="8451.00",
        state_tax="2500.00",
        agi="75500.00",
        magi="80000.00",
        ss_taxable="25500.00",
    )


def test_08_ltcg_stays_in_zero_percent_bracket() -> None:
    result = compute_taxes(
        TaxInput(
            filing_status="single",
            wages=Decimal("20000"),
            ltcg=Decimal("20000"),
            **BASE,
        )
    )
    assert result.ltcg_tax == Decimal("0.00")
    assert result.federal_tax == Decimal("540.00")
    assert result.state_tax == Decimal("2000.00")


def test_09_ltcg_crosses_into_fifteen_percent_bracket() -> None:
    result = compute_taxes(
        TaxInput(
            filing_status="single",
            wages=Decimal("60000"),
            ltcg=Decimal("20000"),
            **BASE,
        )
    )
    assert result.ltcg_tax == Decimal("2756.25")
    assert result.federal_tax == Decimal("7972.25")
    assert result.state_tax == Decimal("4000.00")


def test_10_ltcg_crosses_twenty_percent_bracket() -> None:
    result = compute_taxes(
        TaxInput(
            filing_status="single",
            wages=Decimal("600000"),
            ltcg=Decimal("50000"),
            **BASE,
        )
    )
    assert result.ltcg_tax == Decimal("10000.00")
    assert result.federal_tax == Decimal("185264.75")
    assert result.state_tax == Decimal("32500.00")


def test_11_ma_surtax_crossing() -> None:
    assert_tax_result(
        TaxInput(filing_status="single", wages=Decimal("1100000"), **BASE),
        federal_tax="359785.75",
        state_tax="59000.00",
        agi="1100000.00",
        magi="1100000.00",
    )


def test_12_roth_conversion_only_year() -> None:
    assert_tax_result(
        TaxInput(filing_status="single", roth_conversions=Decimal("80000"), **BASE),
        federal_tax="9441.00",
        state_tax="4000.00",
        agi="80000.00",
        magi="80000.00",
    )


def test_13_mixed_ordinary_ltcg_ss_and_penalty_year() -> None:
    result = compute_taxes(
        TaxInput(
            filing_status="mfj",
            wages=Decimal("90000"),
            pensions_taxable_federal=Decimal("15000"),
            pensions_taxable_state=Decimal("15000"),
            traditional_distributions=Decimal("10000"),
            roth_conversions=Decimal("20000"),
            ltcg=Decimal("30000"),
            ss_gross=Decimal("40000"),
            penalty_eligible_distributions=Decimal("5000"),
            **BASE,
        )
    )
    assert result.federal_tax == Decimal("25362.00")
    assert result.state_tax == Decimal("8250.00")
    assert result.early_withdrawal_penalty == Decimal("500.00")
    assert result.agi == Decimal("199000.00")
    assert result.magi == Decimal("205000.00")
    assert result.ss_taxable_portion == Decimal("34000.00")


def test_mfs_social_security_thresholds_are_zero() -> None:
    assert taxable_social_security(
        Decimal("10000"),
        Decimal("12000"),
        "mfs",
        "2024-33",
    ) == Decimal("8500.00")


def test_hsa_penalty_and_negative_inputs_do_not_create_negative_penalty() -> None:
    early, hsa = compute_early_withdrawal_penalty(Decimal("-1000"), Decimal("1000"))
    assert early == Decimal("0.00")
    assert hsa == Decimal("200.00")


def test_unsupported_state_errors() -> None:
    try:
        compute_taxes(TaxInput(filing_status="single", state="NY", year=2024, ages={}))
    except ValueError as exc:
        assert "Massachusetts" in str(exc)
    else:
        raise AssertionError("Expected unsupported state to raise")


# ---------------------------------------------------------------------------
# apply_brackets — direct unit tests
# ---------------------------------------------------------------------------


def test_apply_brackets_zero_income_returns_zero() -> None:
    brackets = [Bracket(rate=Decimal("0.10"), floor=Decimal("0"), ceiling=Decimal("11600"))]
    assert apply_brackets(Decimal("0"), brackets) == Decimal("0.00")


def test_apply_brackets_negative_income_returns_zero() -> None:
    brackets = [Bracket(rate=Decimal("0.10"), floor=Decimal("0"), ceiling=Decimal("11600"))]
    assert apply_brackets(Decimal("-5000"), brackets) == Decimal("0.00")


def test_apply_brackets_within_first_bracket() -> None:
    brackets = [
        Bracket(rate=Decimal("0.10"), floor=Decimal("0"), ceiling=Decimal("11600")),
        Bracket(rate=Decimal("0.12"), floor=Decimal("11600"), ceiling=Decimal("47150")),
    ]
    assert apply_brackets(Decimal("10000"), brackets) == Decimal("1000.00")


def test_apply_brackets_spans_two_brackets() -> None:
    # $11600 @ 10% = $1160, next $400 @ 12% = $48 → $1208
    brackets = [
        Bracket(rate=Decimal("0.10"), floor=Decimal("0"), ceiling=Decimal("11600")),
        Bracket(rate=Decimal("0.12"), floor=Decimal("11600"), ceiling=Decimal("47150")),
    ]
    assert apply_brackets(Decimal("12000"), brackets) == Decimal("1208.00")


def test_apply_brackets_open_top_bracket() -> None:
    # Single bracket with no ceiling: everything taxed at flat 5%
    brackets = [Bracket(rate=Decimal("0.05"), floor=Decimal("0"), ceiling=None)]
    assert apply_brackets(Decimal("100000"), brackets) == Decimal("5000.00")


# ---------------------------------------------------------------------------
# ordinary_income_excluding_social_security
# ---------------------------------------------------------------------------


def test_ordinary_income_sums_all_sources_excluding_ss() -> None:
    inp = TaxInput(
        year=2024,
        filing_status="single",
        state="MA",
        ages={"primary": 50},
        wages=Decimal("50000"),
        pensions_taxable_federal=Decimal("10000"),
        traditional_distributions=Decimal("5000"),
        roth_conversions=Decimal("3000"),
        sepp_distributions=Decimal("2000"),
        rmd_distributions=Decimal("1000"),
        annuity_taxable=Decimal("500"),
        ss_gross=Decimal("20000"),
        irs_data_version="2024-33",
    )
    assert ordinary_income_excluding_social_security(inp) == Decimal("71500")


def test_ordinary_income_zero_when_only_ss() -> None:
    inp = TaxInput(
        year=2024,
        filing_status="single",
        state="MA",
        ages={"primary": 70},
        ss_gross=Decimal("30000"),
        irs_data_version="2024-33",
    )
    assert ordinary_income_excluding_social_security(inp) == Decimal("0")


# ---------------------------------------------------------------------------
# compute_provisional_income
# ---------------------------------------------------------------------------


def test_compute_provisional_income_adds_half_ss() -> None:
    # 30000 ordinary + 5000 ltcg + 20000/2 SS = 45000
    assert compute_provisional_income(
        Decimal("30000"), Decimal("5000"), Decimal("20000")
    ) == Decimal("45000")


def test_compute_provisional_income_zero_ss() -> None:
    assert compute_provisional_income(
        Decimal("50000"), Decimal("0"), Decimal("0")
    ) == Decimal("50000")


# ---------------------------------------------------------------------------
# apply_ltcg_brackets_stacked
# ---------------------------------------------------------------------------


def test_apply_ltcg_brackets_stacked_all_in_zero_percent_bracket() -> None:
    # ordinary=$0, ltcg=$10000, single 2024 → 0% bracket ceiling=$47025
    tax = apply_ltcg_brackets_stacked(Decimal("0"), Decimal("10000"), 2024, "single", "2024-33")
    assert tax == Decimal("0.00")


def test_apply_ltcg_brackets_stacked_fully_in_fifteen_percent() -> None:
    # ordinary already fills the 0% bracket; all ltcg falls in 15%
    # 0% bracket ceiling for single 2024 is $47025 (confirmed by test_09)
    tax = apply_ltcg_brackets_stacked(Decimal("47025"), Decimal("10000"), 2024, "single", "2024-33")
    assert tax == Decimal("1500.00")


def test_apply_ltcg_brackets_stacked_no_ltcg_returns_zero() -> None:
    tax = apply_ltcg_brackets_stacked(Decimal("50000"), Decimal("0"), 2024, "single", "2024-33")
    assert tax == Decimal("0.00")
