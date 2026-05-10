from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import app.models  # noqa: F401
from app.database import Base
from app.models import Account, Household, Person
from irs_data import (
    get_afr_120_mid_term,
    get_applicable_age,
    get_federal_brackets,
    get_single_life_factor,
    get_standard_deduction,
    get_uniform_lifetime_factor,
    load_table,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


def test_money_type_round_trips_decimal_through_text(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'roundtrip.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        household = Household(
            id="household-1",
            name="Round Trip",
            filing_status="single",
            state="MA",
            created_at="2026-05-09T00:00:00+00:00",
        )
        person = Person(
            id="person-1",
            household_id=household.id,
            name="Taylor",
            dob="1980-01-01",
            retirement_date=None,
            life_expectancy_age=95,
            is_primary=True,
        )
        account = Account(
            id="account-1",
            household_id=household.id,
            owner_person_id=person.id,
            name="Cash",
            account_type="cash",
            current_balance=Decimal("12345.6789"),
            expected_return=Decimal("0.012345"),
            created_at="2026-05-09T00:00:00+00:00",
        )
        session.add_all([household, person, account])
        session.commit()

    with session_factory() as session:
        account = session.scalar(select(Account).where(Account.id == "account-1"))
        assert account is not None
        assert account.current_balance == Decimal("12345.6789")
        assert account.expected_return == Decimal("0.012345")


def test_phase2_model_metadata_contains_spec_tables() -> None:
    expected_tables = {
        "household",
        "person",
        "account",
        "roth_basis",
        "roth_conversion_lot",
        "income_stream",
        "expense_stream",
        "scenario",
        "assumption_set",
        "withdrawal_strategy",
        "sepp_plan",
        "roth_conversion_plan",
        "projection_run_metadata",
        "projection_year",
        "projection_account_balance",
        "projection_warning",
    }

    assert expected_tables.issubset(Base.metadata.tables)


def test_irs_loader_returns_decimals_and_applicable_ages() -> None:
    assert get_applicable_age(date(1948, 6, 30), "2024-33") == Decimal("70.5")
    assert get_applicable_age(date(1949, 7, 1), "2024-33") == Decimal("72")
    assert get_applicable_age(date(1951, 1, 1), "2024-33") == Decimal("73")
    assert get_applicable_age(date(1960, 1, 1), "2024-33") == Decimal("75")
    assert get_single_life_factor(50, "2024-33") == Decimal("36.2")
    assert get_uniform_lifetime_factor(75, "2024-33") == Decimal("24.6")
    assert get_afr_120_mid_term(2024, 8, "2024-33") == Decimal("0.0522")


def test_irs_loader_brackets_and_indexing() -> None:
    brackets = get_federal_brackets(2024, "single", "2024-33")
    assert brackets[0].rate == Decimal("0.10")
    assert brackets[0].floor == Decimal("0")
    assert brackets[0].ceiling == Decimal("11600")

    indexed = get_standard_deduction(2025, "single", "2024-33")
    assert indexed == Decimal("14600") * Decimal("1.025")


def test_load_table_rejects_missing_version() -> None:
    try:
        load_table("manifest", "missing")
    except FileNotFoundError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("Expected missing IRS data version to raise FileNotFoundError")


# ---------------------------------------------------------------------------
# Single life table coverage — guards Bug #2 (table only had ages 49-60).
# ---------------------------------------------------------------------------


def test_single_life_factor_at_age_40_lower_boundary() -> None:
    assert get_single_life_factor(40, "2024-33") == Decimal("45.7")


def test_single_life_factor_at_age_41() -> None:
    assert get_single_life_factor(41, "2024-33") == Decimal("44.8")


def test_single_life_factor_at_age_48() -> None:
    assert get_single_life_factor(48, "2024-33") == Decimal("38.2")


def test_single_life_factor_at_age_49() -> None:
    assert get_single_life_factor(49, "2024-33") == Decimal("37.1")


def test_single_life_factor_at_age_60() -> None:
    assert get_single_life_factor(60, "2024-33") == Decimal("27.1")


def test_single_life_factor_at_age_75_upper_boundary() -> None:
    assert get_single_life_factor(75, "2024-33") == Decimal("14.8")


def test_single_life_factor_below_table_raises_keyerror() -> None:
    try:
        get_single_life_factor(39, "2024-33")
    except KeyError as exc:
        assert "39" in str(exc)
    else:
        raise AssertionError("Expected KeyError for age 39 (below table)")


def test_single_life_factor_above_table_raises_keyerror() -> None:
    try:
        get_single_life_factor(76, "2024-33")
    except KeyError as exc:
        assert "76" in str(exc)
    else:
        raise AssertionError("Expected KeyError for age 76 (above table)")
