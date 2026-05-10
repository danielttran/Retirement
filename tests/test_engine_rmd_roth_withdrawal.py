from __future__ import annotations

from datetime import date
from decimal import Decimal

from irs_data import get_applicable_age
from planner_engine.common import AccountYearState, Person, RothConversionLotState
from planner_engine.rmd import compute_rmd_for_year
from planner_engine.roth import RothConversionPlan, execute_roth_conversion, lot_is_seasoned
from planner_engine.roth.engine import (
    ROTH_ACCOUNT_TYPES,
    TRADITIONAL_ACCOUNT_TYPES,
    is_roth_account,
    is_traditional_account,
    validate_roth_conversion,
)
from planner_engine.withdrawal import (
    DEFAULT_WITHDRAWAL_ORDER,
    execute_withdrawals,
    withdraw_from_roth,
)


def person(pid: str, age: int, year: int = 2024) -> Person:
    return Person(id=pid, dob_year=year - age, age_by_year={year: age})


def account(
    account_id: str,
    account_type: str,
    owner: str = "p1",
    balance: str = "100000",
) -> AccountYearState:
    return AccountYearState(
        id=account_id,
        owner_person_id=owner,
        account_type=account_type,
        balance=Decimal(balance),
    )


def test_rmd_applicable_age_table_edges() -> None:
    assert get_applicable_age(date(1948, 6, 30), "2024-33") == Decimal("70.5")
    assert get_applicable_age(date(1949, 7, 1), "2024-33") == Decimal("72")
    assert get_applicable_age(date(1951, 1, 1), "2024-33") == Decimal("73")
    assert get_applicable_age(date(1960, 1, 1), "2024-33") == Decimal("75")


def test_rmd_uses_joint_table_when_spouse_more_than_ten_years_younger() -> None:
    owner = Person("owner", dob_year=1950, age_by_year={2024: 72})
    spouse = Person("spouse", dob_year=1963, age_by_year={2024: 61})
    ira = account("ira", "traditional_ira", "owner", "298000")
    ira.spouse_beneficiary_person_id = "spouse"
    ira.spouse_is_sole_beneficiary = True

    rmds = compute_rmd_for_year(2024, [ira], [owner, spouse], "2024-33")
    assert rmds["ira"] == Decimal("10000.00")


def test_multiple_traditional_iras_aggregate_to_first_ira() -> None:
    owner = Person("owner", dob_year=1951, age_by_year={2024: 73})
    ira_one = account("ira1", "traditional_ira", "owner", "265000")
    ira_two = account("ira2", "traditional_ira", "owner", "26500")

    rmds = compute_rmd_for_year(2024, [ira_one, ira_two], [owner], "2024-33")
    assert rmds["ira1"] == Decimal("11000.00")
    assert rmds["ira2"] == Decimal("0.00")


def test_multiple_401ks_are_not_aggregated() -> None:
    owner = Person("owner", dob_year=1951, age_by_year={2024: 73})
    first = account("k1", "traditional_401k", "owner", "265000")
    second = account("k2", "traditional_401k", "owner", "53000")

    rmds = compute_rmd_for_year(2024, [first, second], [owner], "2024-33")
    assert rmds["k1"] == Decimal("10000.00")
    assert rmds["k2"] == Decimal("2000.00")


def test_roth_withdrawal_at_age_50_only_contributions_tax_free() -> None:
    owner = person("p1", 50)
    roth = account("r", "roth_ira", balance="50000")
    roth.roth_contributions_basis = Decimal("20000")

    line = withdraw_from_roth(roth, Decimal("10000"), 2024, owner)
    assert line.amount == Decimal("10000.00")
    assert line.ordinary_income == Decimal("0.00")
    assert line.penalty_eligible == Decimal("0.00")


def test_roth_withdrawal_at_age_50_three_year_old_conversion_penalized() -> None:
    owner = person("p1", 50)
    roth = account("r", "roth_ira", balance="50000")
    roth.roth_conversion_lots = [RothConversionLotState(2021, Decimal("10000"))]

    line = withdraw_from_roth(roth, Decimal("8000"), 2024, owner)
    assert line.penalty_eligible == Decimal("8000.00")
    assert line.ordinary_income == Decimal("0.00")


def test_roth_withdrawal_at_age_50_six_year_old_conversion_not_penalized() -> None:
    owner = person("p1", 50)
    roth = account("r", "roth_ira", balance="50000")
    roth.roth_conversion_lots = [RothConversionLotState(2018, Decimal("10000"))]

    line = withdraw_from_roth(roth, Decimal("8000"), 2024, owner)
    assert line.penalty_eligible == Decimal("0.00")
    assert lot_is_seasoned(2018, 2024)


def test_roth_earnings_at_age_60_with_old_first_contribution_qualified() -> None:
    owner = person("p1", 60)
    roth = account("r", "roth_ira", balance="50000")
    roth.roth_first_contribution_year = 2018
    roth.roth_earnings_balance = Decimal("12000")

    line = withdraw_from_roth(roth, Decimal("9000"), 2024, owner)
    assert line.ordinary_income == Decimal("0.00")
    assert line.penalty_eligible == Decimal("0.00")


def test_roth_earnings_at_age_58_with_young_roth_taxed_and_penalized() -> None:
    owner = person("p1", 58)
    roth = account("r", "roth_ira", balance="50000")
    roth.roth_first_contribution_year = 2021
    roth.roth_earnings_balance = Decimal("12000")

    line = withdraw_from_roth(roth, Decimal("9000"), 2024, owner)
    assert line.ordinary_income == Decimal("9000.00")
    assert line.penalty_eligible == Decimal("9000.00")


def test_default_withdrawal_order_takes_unseasoned_roth_conversions_before_earnings() -> None:
    owner = person("p1", 50)
    roth = account("r", "roth_ira", balance="15000")
    roth.roth_conversion_lots = [RothConversionLotState(2022, Decimal("7000"))]
    roth.roth_first_contribution_year = 2022
    roth.roth_earnings_balance = Decimal("8000")

    result = execute_withdrawals(
        Decimal("9000"),
        {"r": roth},
        DEFAULT_WITHDRAWAL_ORDER,
        2024,
        [owner],
        set(),
    )
    assert result.withdrawn == Decimal("9000.00")
    assert result.ordinary_income == Decimal("2000.00")
    assert result.penalty_eligible == Decimal("9000.00")
    assert roth.roth_conversion_lots[0].amount == Decimal("0.00")
    assert roth.roth_earnings_balance == Decimal("6000.00")


def test_hsa_non_medical_at_age_60_ordinary_income_and_hsa_penalty() -> None:
    owner = person("p1", 60)
    hsa = account("hsa", "hsa", balance="10000")
    hsa.hsa_qualified_medical_expense_pct = Decimal("0")

    result = execute_withdrawals(
        Decimal("5000"),
        {"hsa": hsa},
        ["hsa"],
        2024,
        [owner],
        set(),
    )
    assert result.ordinary_income == Decimal("5000.00")
    assert result.hsa_penalty_eligible == Decimal("5000.00")


def test_hsa_non_medical_at_age_66_ordinary_income_no_hsa_penalty() -> None:
    owner = person("p1", 66)
    hsa = account("hsa", "hsa", balance="10000")
    hsa.hsa_qualified_medical_expense_pct = Decimal("0")

    result = execute_withdrawals(
        Decimal("5000"),
        {"hsa": hsa},
        ["hsa"],
        2024,
        [owner],
        set(),
    )
    assert result.ordinary_income == Decimal("5000.00")
    assert result.hsa_penalty_eligible == Decimal("0.00")


def test_withdrawal_engine_respects_sepp_lockout() -> None:
    owner = person("p1", 55)
    locked = account("ira", "traditional_ira", balance="100000")
    cash = account("cash", "cash", balance="10000")

    result = execute_withdrawals(
        Decimal("15000"),
        {"ira": locked, "cash": cash},
        DEFAULT_WITHDRAWAL_ORDER,
        2024,
        [owner],
        {"ira"},
    )
    assert result.withdrawn == Decimal("10000.00")
    assert locked.balance == Decimal("100000")


def test_taxable_brokerage_withdrawal_produces_ltcg() -> None:
    owner = person("p1", 55)
    brokerage = account("taxable", "taxable_brokerage", balance="10000")
    brokerage.cost_basis_pct = Decimal("0.70")

    result = execute_withdrawals(
        Decimal("1000"),
        {"taxable": brokerage},
        ["taxable_brokerage"],
        2024,
        [owner],
        set(),
    )
    assert result.ltcg == Decimal("300.00")


def test_roth_conversion_executes_and_creates_lot() -> None:
    source = account("trad", "traditional_ira", balance="100000")
    dest = account("roth", "roth_ira", balance="5000")
    cash = account("cash", "cash", balance="10000")
    state = {"trad": source, "roth": dest, "cash": cash}

    result = execute_roth_conversion(
        RothConversionPlan("trad", "roth", 2024, Decimal("25000"), "cash", Decimal("5000")),
        state,
    )
    assert result.issues == []
    assert result.roth_conversions_taxable == Decimal("25000")
    assert source.balance == Decimal("75000")
    assert dest.balance == Decimal("30000")
    assert cash.balance == Decimal("5000")
    assert dest.roth_conversion_lots[0].conversion_year == 2024


def test_roth_conversion_validation_errors() -> None:
    cash = account("cash", "cash", balance="1000")
    roth = account("roth", "roth_ira", balance="0")
    state = {"cash": cash, "roth": roth}

    result = execute_roth_conversion(
        RothConversionPlan("cash", "cash", 2024, Decimal("2000"), "cash", Decimal("2000")),
        state,
    )
    codes = {issue.code for issue in result.issues}
    assert "roth_conv_invalid_source" in codes
    assert "roth_conv_invalid_dest" in codes
    assert "roth_conv_insufficient_source" in codes
    assert "roth_conv_tax_payment_insufficient" in codes


# ---------------------------------------------------------------------------
# Roth predicate functions
# ---------------------------------------------------------------------------


def test_is_traditional_account_all_types() -> None:
    for t in TRADITIONAL_ACCOUNT_TYPES:
        assert is_traditional_account(t) is True, f"{t} should be traditional"


def test_is_traditional_account_rejects_roth_and_other() -> None:
    for t in [*ROTH_ACCOUNT_TYPES, "cash", "hsa", "taxable_brokerage", "real_estate", "debt"]:
        assert is_traditional_account(t) is False, f"{t} should not be traditional"


def test_is_roth_account_all_types() -> None:
    for t in ROTH_ACCOUNT_TYPES:
        assert is_roth_account(t) is True, f"{t} should be roth"


def test_is_roth_account_rejects_traditional_and_other() -> None:
    for t in [*TRADITIONAL_ACCOUNT_TYPES, "cash", "hsa", "taxable_brokerage"]:
        assert is_roth_account(t) is False, f"{t} should not be roth"


def test_lot_is_seasoned_exactly_five_years() -> None:
    assert lot_is_seasoned(2019, 2024) is True


def test_lot_is_seasoned_four_years_is_not() -> None:
    assert lot_is_seasoned(2020, 2024) is False


def test_lot_is_seasoned_six_years() -> None:
    assert lot_is_seasoned(2018, 2024) is True


# ---------------------------------------------------------------------------
# validate_roth_conversion — standalone error paths
# ---------------------------------------------------------------------------


def test_validate_roth_conversion_missing_source_key() -> None:
    roth = account("roth", "roth_ira", balance="10000")
    issues = validate_roth_conversion(
        RothConversionPlan("nonexistent", "roth", 2024, Decimal("5000")),
        {"roth": roth},
    )
    codes = {i.code for i in issues}
    assert "roth_conv_invalid_source" in codes


def test_validate_roth_conversion_missing_dest_key() -> None:
    trad = account("trad", "traditional_ira", balance="10000")
    issues = validate_roth_conversion(
        RothConversionPlan("trad", "nonexistent", 2024, Decimal("5000")),
        {"trad": trad},
    )
    codes = {i.code for i in issues}
    assert "roth_conv_invalid_dest" in codes


def test_validate_roth_conversion_amount_exceeds_balance() -> None:
    trad = account("trad", "traditional_ira", balance="3000")
    roth = account("roth", "roth_ira", balance="0")
    issues = validate_roth_conversion(
        RothConversionPlan("trad", "roth", 2024, Decimal("5000")),
        {"trad": trad, "roth": roth},
    )
    codes = {i.code for i in issues}
    assert "roth_conv_insufficient_source" in codes


def test_validate_roth_conversion_clean_path_has_no_issues() -> None:
    trad = account("trad", "traditional_ira", balance="50000")
    roth = account("roth", "roth_ira", balance="0")
    issues = validate_roth_conversion(
        RothConversionPlan("trad", "roth", 2024, Decimal("10000")),
        {"trad": trad, "roth": roth},
    )
    assert issues == []
