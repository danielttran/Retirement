"""Medicare IRMAA (Income-Related Monthly Adjustment Amount) surcharges.

IRMAA adds a monthly surcharge to Medicare Part B and Part D premiums when MAGI from two years
prior exceeds published thresholds. Pure Decimal functions; thresholds indexed forward from the
data file's base year.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

from irs_data import load_table

CENT = Decimal("0.01")
ZERO = Decimal("0")
ONE = Decimal("1")
MONTHS = Decimal("12")

# Filing statuses collapse to the three IRMAA schedules.
_STATUS_MAP = {
    "single": "single",
    "hoh": "single",
    "qw": "single",
    "mfj": "mfj",
    "mfs": "mfs",
}


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def irmaa_monthly_surcharge(
    magi: Decimal,
    filing_status: str,
    year: int,
    irs_data_version: str,
    indexing_rate: Decimal,
) -> Decimal:
    """Combined Part B + Part D monthly IRMAA surcharge for one beneficiary."""
    table = cast(dict[str, Any], load_table("irmaa_thresholds", irs_data_version))
    base_year = int(cast(str, table["baseYear"]))
    schedule = cast(
        list[dict[str, Decimal]], table[_STATUS_MAP.get(filing_status, "single")]
    )
    factor = (ONE + indexing_rate) ** (year - base_year)
    surcharge = ZERO
    for tier in schedule:
        if magi >= tier["magiFloor"] * factor:
            surcharge = tier["partB"] + tier["partD"]
    return surcharge


# Rough 2024 national annual Medicare costs per person (Part B base + Part D + Medigap + dental).
_MEDICARE_BASE_ANNUAL = Decimal("174.70") * MONTHS  # Part B standard
_MEDICARE_PART_D_ANNUAL = Decimal("55.50") * MONTHS  # average Part D premium
_MEDIGAP_ANNUAL = Decimal("150.00") * MONTHS  # Plan G-style supplement
_DENTAL_VISION_ANNUAL = Decimal("50.00") * MONTHS
# Health-status multipliers reflecting differing out-of-pocket costs.
_HEALTH_MULTIPLIER = {
    "excellent": Decimal("0.90"),
    "good": Decimal("1.00"),
    "poor": Decimal("1.25"),
}


def estimate_medicare_annual(
    health: str = "good",
    include_dental_vision: bool = True,
) -> Decimal:
    """Estimated annual Medicare cost per person at 65+ (premiums + supplement, before IRMAA).

    A national rough estimate (Boldin uses state-specific data we cannot access locally). IRMAA
    surcharges are computed separately via ``irmaa_annual_surcharge``.
    """
    base = _MEDICARE_BASE_ANNUAL + _MEDICARE_PART_D_ANNUAL + _MEDIGAP_ANNUAL
    if include_dental_vision:
        base += _DENTAL_VISION_ANNUAL
    multiplier = _HEALTH_MULTIPLIER.get(health, ONE)
    return _quantize(base * multiplier)


def irmaa_annual_surcharge(
    magi: Decimal,
    filing_status: str,
    enrolled_count: int,
    year: int,
    irs_data_version: str,
    indexing_rate: Decimal,
) -> Decimal:
    """Annual IRMAA cost = monthly surcharge x 12 x number of Medicare-enrolled people (65+)."""
    if enrolled_count <= 0:
        return ZERO
    monthly = irmaa_monthly_surcharge(magi, filing_status, year, irs_data_version, indexing_rate)
    return _quantize(monthly * MONTHS * Decimal(enrolled_count))
