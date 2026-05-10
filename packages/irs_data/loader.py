from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any, cast

DATA_ROOT = Path(__file__).resolve().parent
DEFAULT_INDEXING_RATE = Decimal("0.025")


@dataclass(frozen=True)
class Bracket:
    rate: Decimal
    floor: Decimal
    ceiling: Decimal | None


def _decimalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _decimalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decimalize(item) for item in value]
    if isinstance(value, str):
        try:
            return Decimal(value)
        except Exception:
            return value
    return value


@cache
def load_table(name: str, version: str) -> dict[str, Any] | list[Any]:
    path = DATA_ROOT / version / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"IRS table {name!r} not found for version {version!r}")
    with path.open("r", encoding="utf-8") as handle:
        return cast(dict[str, Any] | list[Any], _decimalize(json.load(handle)))


def get_afr_120_mid_term(year: int, month: int, version: str) -> Decimal:
    table = cast(dict[str, dict[str, Decimal]], load_table("afr_120_mid_term", version))
    try:
        return table[str(year)][f"{month:02d}"]
    except KeyError as exc:
        raise KeyError(f"Missing AFR for {year}-{month:02d} in {version}") from exc


def _factor_from_table(name: str, age: int, version: str) -> Decimal:
    rows = cast(list[dict[str, Decimal]], load_table(name, version))
    for row in rows:
        if int(row["age"]) == age:
            return row["factor"]
    raise KeyError(f"Missing {name} factor for age {age} in {version}")


def get_single_life_factor(age: int, version: str) -> Decimal:
    return _factor_from_table("single_life_table", age, version)


def get_uniform_lifetime_factor(age: int, version: str) -> Decimal:
    return _factor_from_table("uniform_lifetime_table", age, version)


def get_joint_life_factor(owner_age: int, beneficiary_age: int, version: str) -> Decimal:
    rows = cast(list[dict[str, Decimal]], load_table("joint_last_survivor_table", version))
    for row in rows:
        if int(row["ownerAge"]) == owner_age and int(row["beneficiaryAge"]) == beneficiary_age:
            return row["factor"]
    raise KeyError(
        "Missing joint last survivor factor for "
        f"owner age {owner_age}, beneficiary age {beneficiary_age} in {version}"
    )


def get_applicable_age(dob: date, version: str) -> Decimal:
    rows = cast(list[dict[str, Decimal | str | None]], load_table("applicable_age", version))
    for row in rows:
        start = date.fromisoformat(cast(str, row["birthDateStart"]))
        end_value = row["birthDateEnd"]
        end = date.max if end_value is None else date.fromisoformat(cast(str, end_value))
        if start <= dob <= end:
            return cast(Decimal, row["applicableAge"])
    raise KeyError(f"No applicable-age rule for DOB {dob.isoformat()} in {version}")


def _year_table_entry(table_name: str, year: int, version: str) -> tuple[int, dict[str, Any]]:
    table = cast(dict[str, dict[str, Any]], load_table(table_name, version))
    available_years = sorted(int(key) for key in table)
    source_year = max(
        (candidate for candidate in available_years if candidate <= year),
        default=None,
    )
    if source_year is None:
        raise KeyError(f"No {table_name} data for {year} in {version}")
    return source_year, table[str(source_year)]


def _index_amount(value: Decimal, source_year: int, target_year: int) -> Decimal:
    years = target_year - source_year
    return value * ((Decimal("1") + DEFAULT_INDEXING_RATE) ** years)


def _required_decimal(value: Decimal | None) -> Decimal:
    if value is None:
        raise ValueError("Expected Decimal value, got None")
    return value


def get_federal_brackets(year: int, filing_status: str, version: str) -> list[Bracket]:
    source_year, table = _year_table_entry("federal_brackets", year, version)
    rows = cast(list[dict[str, Decimal | None]], table[filing_status])
    return [
        Bracket(
            rate=_required_decimal(row["rate"]),
            floor=_index_amount(_required_decimal(row["floor"]), source_year, year),
            ceiling=None
            if row["ceiling"] is None
            else _index_amount(row["ceiling"], source_year, year),
        )
        for row in rows
    ]


def get_standard_deduction(year: int, filing_status: str, version: str) -> Decimal:
    source_year, table = _year_table_entry("standard_deduction", year, version)
    return _index_amount(cast(Decimal, table[filing_status]), source_year, year)
