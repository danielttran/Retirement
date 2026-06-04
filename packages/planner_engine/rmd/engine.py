from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from irs_data import get_applicable_age, get_joint_life_factor, get_uniform_lifetime_factor

from planner_engine.common import AccountYearState, Person

CENT = Decimal("0.01")
RMD_ACCOUNT_TYPES = {
    "traditional_ira",
    "traditional_401k",
    "traditional_403b",
    "governmental_457b",
}


def quantize_cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def rmd_applicable_for_person(person: Person, year: int, irs_data_version: str) -> bool:
    attained_age = Decimal(person.age_in_year(year))
    applicable_age = get_applicable_age_from_year(person.dob_year, irs_data_version)
    return attained_age >= applicable_age


def get_applicable_age_from_year(dob_year: int, irs_data_version: str) -> Decimal:
    from datetime import date

    return get_applicable_age(date(dob_year, 1, 1), irs_data_version)


def compute_rmd_for_year(
    year: int,
    accounts: list[AccountYearState],
    persons: list[Person],
    irs_data_version: str,
) -> dict[str, Decimal]:
    people = {person.id: person for person in persons}
    obligations: dict[str, Decimal] = {}

    ira_accounts: list[tuple[AccountYearState, Decimal]] = []
    for account in accounts:
        if account.account_type not in RMD_ACCOUNT_TYPES:
            continue
        if account.exclude_from_withdrawals:
            continue
        owner = people[account.owner_person_id]
        owner_age = owner.age_in_year(year)
        if Decimal(owner_age) < get_applicable_age_from_year(owner.dob_year, irs_data_version):
            continue
        divisor = _rmd_divisor(account, people, owner_age, year, irs_data_version)
        rmd = quantize_cents(account.balance / divisor)
        if account.account_type == "traditional_ira":
            ira_accounts.append((account, rmd))
        else:
            obligations[account.id] = rmd

    if ira_accounts:
        total_ira_rmd = sum((rmd for _, rmd in ira_accounts), Decimal("0"))
        first_ira = ira_accounts[0][0]
        obligations[first_ira.id] = quantize_cents(total_ira_rmd)
        for account, _ in ira_accounts[1:]:
            obligations[account.id] = Decimal("0.00")

    return obligations


def _rmd_divisor(
    account: AccountYearState,
    people: dict[str, Person],
    owner_age: int,
    year: int,
    irs_data_version: str,
) -> Decimal:
    if account.spouse_is_sole_beneficiary and account.spouse_beneficiary_person_id is not None:
        spouse = people[account.spouse_beneficiary_person_id]
        spouse_age = spouse.age_in_year(year)
        if owner_age - spouse_age > 10:
            return get_joint_life_factor(owner_age, spouse_age, irs_data_version)
    return get_uniform_lifetime_factor(owner_age, irs_data_version)
