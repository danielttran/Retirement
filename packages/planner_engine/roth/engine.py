from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from planner_engine.common import AccountYearState, RothConversionLotState

TRADITIONAL_ACCOUNT_TYPES = {"traditional_ira", "traditional_401k", "traditional_403b"}
ROTH_ACCOUNT_TYPES = {"roth_ira", "roth_401k"}


@dataclass(frozen=True)
class RothIssue:
    severity: Literal["warning", "error"]
    code: str
    message: str


@dataclass(frozen=True)
class RothConversionPlan:
    source_account_id: str
    destination_account_id: str
    year: int
    amount: Decimal
    tax_payment_source_account_id: str | None = None
    estimated_tax_cost: Decimal = Decimal("0")


@dataclass(frozen=True)
class RothConversionResult:
    roth_conversions_taxable: Decimal
    issues: list[RothIssue]


def is_traditional_account(account_type: str) -> bool:
    return account_type in TRADITIONAL_ACCOUNT_TYPES


def is_roth_account(account_type: str) -> bool:
    return account_type in ROTH_ACCOUNT_TYPES


def lot_is_seasoned(conversion_year: int, current_year: int) -> bool:
    return current_year >= conversion_year + 5


def execute_roth_conversion(
    plan: RothConversionPlan,
    accounts_state: dict[str, AccountYearState],
) -> RothConversionResult:
    issues = validate_roth_conversion(plan, accounts_state)
    if any(issue.severity == "error" for issue in issues):
        return RothConversionResult(Decimal("0"), issues)

    source = accounts_state[plan.source_account_id]
    destination = accounts_state[plan.destination_account_id]
    tax_source = accounts_state.get(plan.tax_payment_source_account_id or "")

    source.balance -= plan.amount
    destination.balance += plan.amount
    destination.roth_conversion_lots.append(
        RothConversionLotState(
            conversion_year=plan.year,
            amount=plan.amount,
            taxable_conversion=True,
        )
    )
    if tax_source is not None and plan.estimated_tax_cost > Decimal("0"):
        tax_source.balance -= plan.estimated_tax_cost
    return RothConversionResult(plan.amount, issues)


def validate_roth_conversion(
    plan: RothConversionPlan,
    accounts_state: dict[str, AccountYearState],
) -> list[RothIssue]:
    issues: list[RothIssue] = []
    source = accounts_state.get(plan.source_account_id)
    destination = accounts_state.get(plan.destination_account_id)

    if source is None or not is_traditional_account(source.account_type):
        issues.append(
            RothIssue("error", "roth_conv_invalid_source", "Source is not a traditional account.")
        )
    if destination is None or not is_roth_account(destination.account_type):
        issues.append(RothIssue("error", "roth_conv_invalid_dest", "Destination is not Roth."))
    if source is not None and plan.amount > source.balance:
        issues.append(
            RothIssue(
                "error",
                "roth_conv_insufficient_source",
                "Conversion amount exceeds source balance.",
            )
        )
    tax_source_id = plan.tax_payment_source_account_id
    if tax_source_id is not None:
        tax_source = accounts_state.get(tax_source_id)
        if tax_source is None or tax_source.balance < plan.estimated_tax_cost:
            issues.append(
                RothIssue(
                    "error",
                    "roth_conv_tax_payment_insufficient",
                    "Tax payment source has insufficient funds.",
                )
            )

    return issues
