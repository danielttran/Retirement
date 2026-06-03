from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class Person:
    id: str
    dob_year: int
    age_by_year: dict[int, int] = field(default_factory=dict)

    def age_in_year(self, year: int) -> int:
        if year in self.age_by_year:
            return self.age_by_year[year]
        return year - self.dob_year


@dataclass
class RothConversionLotState:
    conversion_year: int
    amount: Decimal
    taxable_conversion: bool = True


@dataclass
class AccountYearState:
    id: str
    owner_person_id: str
    account_type: str
    balance: Decimal
    expected_return: Decimal = Decimal("0")
    cost_basis_pct: Decimal | None = None
    roth_first_contribution_year: int | None = None
    roth_contributions_basis: Decimal = Decimal("0")
    roth_earnings_balance: Decimal = Decimal("0")
    roth_conversion_lots: list[RothConversionLotState] = field(default_factory=list)
    hsa_qualified_medical_expense_pct: Decimal = Decimal("1")
    spouse_beneficiary_person_id: str | None = None
    spouse_is_sole_beneficiary: bool = False
    # Debt accounts only: scheduled annual principal+interest payment. ``balance`` is the amount
    # owed (positive) and ``expected_return`` is the loan APR.
    debt_annual_payment: Decimal = Decimal("0")
    exclude_from_withdrawals: bool = False

