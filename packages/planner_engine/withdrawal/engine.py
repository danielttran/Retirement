from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from planner_engine.common import AccountYearState, Person
from planner_engine.roth import lot_is_seasoned

CENT = Decimal("0.01")
DEFAULT_WITHDRAWAL_ORDER = [
    "cash",
    "taxable_brokerage",
    "traditional",
    "roth_contributions",
    "roth_conversions_seasoned",
    "hsa",
    "roth_earnings",
]


@dataclass(frozen=True)
class WithdrawalLine:
    account_id: str
    layer: str
    amount: Decimal
    ordinary_income: Decimal = Decimal("0")
    ltcg: Decimal = Decimal("0")
    penalty_eligible: Decimal = Decimal("0")
    hsa_penalty_eligible: Decimal = Decimal("0")


@dataclass(frozen=True)
class WithdrawalResult:
    requested: Decimal
    withdrawn: Decimal
    ordinary_income: Decimal
    ltcg: Decimal
    penalty_eligible: Decimal
    hsa_penalty_eligible: Decimal
    lines: list[WithdrawalLine] = field(default_factory=list)


def quantize_cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def execute_withdrawals(
    target_amount: Decimal,
    accounts_state: dict[str, AccountYearState],
    order: list[str],
    year: int,
    persons: list[Person],
    sepp_locked_account_ids: set[str],
) -> WithdrawalResult:
    remaining = target_amount
    lines: list[WithdrawalLine] = []
    people = {person.id: person for person in persons}

    # Within a bucket, deplete the lowest-expected-return accounts first so higher-returning
    # accounts compound longer (matches Boldin's rate-of-return-ordered drawdown).
    ordered_accounts = sorted(accounts_state.values(), key=lambda a: a.expected_return)

    for bucket in order:
        if remaining <= Decimal("0"):
            break
        for account in ordered_accounts:
            if remaining <= Decimal("0"):
                break
            is_locked = account.id in sepp_locked_account_ids or account.exclude_from_withdrawals
            if is_locked or not _account_matches_bucket(account, bucket):
                continue
            owner = people[account.owner_person_id]
            line = _withdraw_from_account(account, bucket, remaining, year, owner)
            if line.amount <= Decimal("0"):
                continue
            remaining -= line.amount
            lines.append(line)

    withdrawn = target_amount - max(remaining, Decimal("0"))
    return WithdrawalResult(
        requested=target_amount,
        withdrawn=quantize_cents(withdrawn),
        ordinary_income=quantize_cents(sum((line.ordinary_income for line in lines), Decimal("0"))),
        ltcg=quantize_cents(sum((line.ltcg for line in lines), Decimal("0"))),
        penalty_eligible=quantize_cents(
            sum((line.penalty_eligible for line in lines), Decimal("0"))
        ),
        hsa_penalty_eligible=quantize_cents(
            sum((line.hsa_penalty_eligible for line in lines), Decimal("0"))
        ),
        lines=lines,
    )


def _account_matches_bucket(account: AccountYearState, bucket: str) -> bool:
    if bucket == "cash":
        return account.account_type == "cash"
    if bucket == "taxable_brokerage":
        return account.account_type == "taxable_brokerage"
    if bucket == "traditional":
        return account.account_type in {"traditional_ira", "traditional_401k", "traditional_403b"}
    if bucket.startswith("roth_"):
        return account.account_type in {"roth_ira", "roth_401k"}
    if bucket == "hsa":
        return account.account_type == "hsa"
    return account.account_type == bucket


def _withdraw_from_account(
    account: AccountYearState,
    bucket: str,
    requested: Decimal,
    year: int,
    owner: Person,
) -> WithdrawalLine:
    if bucket == "roth_contributions":
        return withdraw_from_roth(account, requested, year, owner, "contributions")
    if bucket == "roth_conversions_seasoned":
        return withdraw_from_roth(account, requested, year, owner, "seasoned_conversions")
    if bucket == "roth_earnings":
        return withdraw_from_roth(account, requested, year, owner, "all")
    if account.account_type == "taxable_brokerage":
        amount = _take_balance(account, requested)
        basis_pct = account.cost_basis_pct if account.cost_basis_pct is not None else Decimal("1")
        gain = quantize_cents(amount * (Decimal("1") - basis_pct))
        return WithdrawalLine(account.id, "taxable_brokerage", amount, ltcg=gain)
    if account.account_type in {"traditional_ira", "traditional_401k", "traditional_403b"}:
        amount = _take_balance(account, requested)
        penalty = amount if owner.age_in_year(year) < 59 else Decimal("0")
        return WithdrawalLine(
            account.id,
            "traditional",
            amount,
            ordinary_income=amount,
            penalty_eligible=penalty,
        )
    if account.account_type == "hsa":
        return _withdraw_hsa(account, requested, owner.age_in_year(year))
    if account.account_type == "deferred_comp":
        # Non-qualified deferred comp: ordinary income on distribution, no early penalty.
        amount = _take_balance(account, requested)
        return WithdrawalLine(account.id, "deferred_comp", amount, ordinary_income=amount)
    # 529 and life-insurance cash value: tax-free for the modeled use (education / policy loans).
    amount = _take_balance(account, requested)
    return WithdrawalLine(account.id, account.account_type, amount)


def _take_balance(account: AccountYearState, requested: Decimal) -> Decimal:
    amount = quantize_cents(min(account.balance, requested))
    account.balance -= amount
    return amount


RothLayer = Literal["contributions", "seasoned_conversions", "earnings", "all"]


def withdraw_from_roth(
    account: AccountYearState,
    requested: Decimal,
    year: int,
    owner: Person,
    layer: RothLayer = "all",
) -> WithdrawalLine:
    if layer == "contributions":
        amount = quantize_cents(min(requested, account.roth_contributions_basis, account.balance))
        account.roth_contributions_basis -= amount
        account.balance -= amount
        return WithdrawalLine(account.id, "roth_contributions", amount)
    if layer == "seasoned_conversions":
        return _withdraw_roth_conversions(account, requested, year, seasoned=True)
    if layer == "earnings":
        return _withdraw_roth_earnings(account, requested, year, owner)

    lines = [
        withdraw_from_roth(account, requested, year, owner, "contributions"),
    ]
    remaining = requested - lines[-1].amount
    lines.append(_withdraw_roth_conversions(account, remaining, year, seasoned=True))
    remaining -= lines[-1].amount
    lines.append(_withdraw_roth_conversions(account, remaining, year, seasoned=False))
    remaining -= lines[-1].amount
    lines.append(_withdraw_roth_earnings(account, remaining, year, owner))
    return _combine_lines(account.id, "roth", lines)


def _withdraw_roth_conversions(
    account: AccountYearState,
    requested: Decimal,
    year: int,
    seasoned: bool,
) -> WithdrawalLine:
    remaining = requested
    withdrawn = Decimal("0")
    penalty = Decimal("0")
    for lot in sorted(account.roth_conversion_lots, key=lambda item: item.conversion_year):
        if remaining <= Decimal("0"):
            break
        if lot_is_seasoned(lot.conversion_year, year) != seasoned:
            continue
        amount = quantize_cents(min(lot.amount, remaining, account.balance))
        lot.amount -= amount
        account.balance -= amount
        withdrawn += amount
        remaining -= amount
        if not seasoned and lot.taxable_conversion:
            penalty += amount
    layer = "roth_conversions_seasoned" if seasoned else "roth_conversions_unseasoned"
    return WithdrawalLine(
        account.id,
        layer,
        quantize_cents(withdrawn),
        penalty_eligible=quantize_cents(penalty),
    )


def _withdraw_roth_earnings(
    account: AccountYearState,
    requested: Decimal,
    year: int,
    owner: Person,
) -> WithdrawalLine:
    amount = quantize_cents(min(requested, account.roth_earnings_balance, account.balance))
    account.roth_earnings_balance -= amount
    account.balance -= amount
    first_year = account.roth_first_contribution_year
    qualified = first_year is not None and owner.age_in_year(year) >= 60 and year >= first_year + 5
    ordinary = Decimal("0") if qualified else amount
    penalty = Decimal("0") if qualified else amount
    return WithdrawalLine(
        account.id,
        "roth_earnings",
        amount,
        ordinary_income=ordinary,
        penalty_eligible=penalty,
    )


def _withdraw_hsa(account: AccountYearState, requested: Decimal, owner_age: int) -> WithdrawalLine:
    amount = _take_balance(account, requested)
    qualified = quantize_cents(amount * account.hsa_qualified_medical_expense_pct)
    non_medical = amount - qualified
    hsa_penalty = non_medical if owner_age < 65 else Decimal("0")
    return WithdrawalLine(
        account.id,
        "hsa",
        amount,
        ordinary_income=non_medical,
        hsa_penalty_eligible=hsa_penalty,
    )


def _combine_lines(account_id: str, layer: str, lines: list[WithdrawalLine]) -> WithdrawalLine:
    return WithdrawalLine(
        account_id=account_id,
        layer=layer,
        amount=quantize_cents(sum((line.amount for line in lines), Decimal("0"))),
        ordinary_income=quantize_cents(sum((line.ordinary_income for line in lines), Decimal("0"))),
        ltcg=quantize_cents(sum((line.ltcg for line in lines), Decimal("0"))),
        penalty_eligible=quantize_cents(
            sum((line.penalty_eligible for line in lines), Decimal("0"))
        ),
        hsa_penalty_eligible=quantize_cents(
            sum((line.hsa_penalty_eligible for line in lines), Decimal("0"))
        ),
    )
