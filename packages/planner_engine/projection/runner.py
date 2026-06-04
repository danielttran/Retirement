from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol
from uuid import uuid4

from planner_engine.common import AccountYearState, Person, RothConversionLotState
from planner_engine.rmd import compute_rmd_for_year
from planner_engine.roth import RothConversionPlan, execute_roth_conversion
from planner_engine.tax import TaxInput, TaxResult, compute_taxes, irmaa_annual_surcharge
from planner_engine.withdrawal import (
    DEFAULT_WITHDRAWAL_ORDER,
    WithdrawalResult,
    execute_withdrawals,
)

CENT = Decimal("0.01")
ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True)
class AssumptionSet:
    cpi_rate: Decimal = Decimal("0.025")
    healthcare_inflation_rate: Decimal = Decimal("0.04")
    ss_cola_rate: Decimal = Decimal("0.025")
    pension_cola_rate: Decimal = Decimal("0")
    bracket_indexing_rate: Decimal = Decimal("0.025")
    cash_reserve_target_months: int = 24
    tax_iteration_max: int = 5
    tax_iteration_tolerance: Decimal = Decimal("1.00")


@dataclass(frozen=True)
class IncomeStream:
    id: str
    kind: str
    annual_amount: Decimal
    start_year: int
    end_year: int | None = None
    inflation_kind: str = "cpi"
    custom_inflation_rate: Decimal | None = None
    person_id: str | None = None
    is_taxable_federal: bool = True
    is_taxable_state: bool = True
    claiming_age: int | None = None


@dataclass(frozen=True)
class ExpenseStream:
    id: str
    kind: str
    annual_amount: Decimal
    start_year: int
    end_year: int | None = None
    inflation_kind: str = "cpi"
    custom_inflation_rate: Decimal | None = None


@dataclass(frozen=True)
class SeppProjectionPlan:
    id: str
    account_id: str
    method: str
    status: str
    start_year: int
    required_end_year: int
    annual_payment: Decimal


# Account types whose employee elective deferrals are excluded from federal taxable wages.
FEDERAL_PRETAX_ACCOUNT_TYPES = {
    "traditional_401k",
    "traditional_403b",
    "governmental_457b",
    "traditional_ira",
    "hsa",
}
# MA excludes employer-plan elective deferrals from state wages but NOT traditional IRA/HSA.
STATE_PRETAX_ACCOUNT_TYPES = {
    "traditional_401k",
    "traditional_403b",
    "governmental_457b",
}
ROTH_ACCOUNT_TYPES = {"roth_ira", "roth_401k"}


@dataclass(frozen=True)
class ContributionPlan:
    """A recurring savings contribution into an account during the accumulation phase.

    ``annual_amount`` is the employee contribution in ``start_year`` dollars.
    ``employer_match_amount`` is added on top (free money: it increases net worth and is never an
    outflow from the budget). Pre-tax employee contributions reduce taxable wages per account type.
    """

    account_id: str
    annual_amount: Decimal
    start_year: int
    end_year: int | None = None
    inflation_kind: str = "cpi"
    custom_inflation_rate: Decimal | None = None
    employer_match_amount: Decimal = ZERO


@dataclass(frozen=True)
class ScenarioInput:
    id: str
    filing_status: str
    state: str
    start_year: int
    end_year: int
    primary_person_id: str
    people: list[Person]
    accounts: list[AccountYearState]
    income_streams: list[IncomeStream] = field(default_factory=list)
    expense_streams: list[ExpenseStream] = field(default_factory=list)
    assumptions: AssumptionSet = field(default_factory=AssumptionSet)
    withdrawal_order: list[str] = field(default_factory=lambda: list(DEFAULT_WITHDRAWAL_ORDER))
    surplus_target_account_id: str | None = None
    sepp_plans: list[SeppProjectionPlan] = field(default_factory=list)
    roth_conversion_plans: list[RothConversionPlan] = field(default_factory=list)
    contribution_plans: list[ContributionPlan] = field(default_factory=list)
    spouse_person_id: str | None = None
    # Optional per-account, per-year return overrides (account_id -> year -> rate). Used by the
    # Monte Carlo driver to inject sampled returns while keeping the engine deterministic + Decimal.
    return_overrides: dict[str, dict[int, Decimal]] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectionRunMetadata:
    id: str
    scenario_id: str
    run_at: str
    engine_version: str
    irs_data_version: str
    assumption_snapshot: dict[str, str | int]
    convergence_log: list[dict[str, str | int]]


@dataclass(frozen=True)
class ProjectionYear:
    id: str
    scenario_id: str
    year: int
    age_primary: int
    age_spouse: int | None
    gross_income: Decimal
    required_distributions: Decimal
    flexible_withdrawals: Decimal
    roth_conversions: Decimal
    expenses: Decimal
    federal_tax: Decimal
    state_tax: Decimal
    early_withdrawal_penalty: Decimal
    magi: Decimal
    provisional_income: Decimal
    ss_taxable_portion: Decimal
    ordinary_taxable_income: Decimal
    medicare_irmaa: Decimal
    surplus: Decimal
    ending_net_worth: Decimal


@dataclass(frozen=True)
class ProjectionAccountBalance:
    id: str
    scenario_id: str
    year: int
    account_id: str
    beginning_balance: Decimal
    contributions: Decimal
    distributions: Decimal
    investment_return: Decimal
    ending_balance: Decimal


@dataclass(frozen=True)
class ProjectionWarning:
    id: str
    scenario_id: str
    year: int | None
    severity: str
    code: str
    message: str


ILLIQUID_ACCOUNT_TYPES = {"real_estate", "debt"}


@dataclass(frozen=True)
class ProjectionSummary:
    """Headline plan metrics (Boldin-style): lifetime taxes, out-of-savings age, estate value."""

    final_year: int
    final_age: int
    estate_net_worth: Decimal
    peak_net_worth: Decimal
    peak_net_worth_year: int
    lifetime_federal_tax: Decimal
    lifetime_state_tax: Decimal
    lifetime_penalties: Decimal
    lifetime_total_tax: Decimal
    total_lifetime_income: Decimal
    total_lifetime_expenses: Decimal
    total_lifetime_roth_conversions: Decimal
    total_lifetime_irmaa: Decimal
    out_of_savings_year: int | None
    out_of_savings_age: int | None


@dataclass(frozen=True)
class ProjectionRun:
    metadata: ProjectionRunMetadata
    years: list[ProjectionYear]
    account_balances: list[ProjectionAccountBalance]
    warnings: list[ProjectionWarning]
    summary: ProjectionSummary


class _YearLike(Protocol):
    @property
    def year(self) -> int: ...
    @property
    def age_primary(self) -> int: ...
    @property
    def ending_net_worth(self) -> Decimal: ...
    @property
    def federal_tax(self) -> Decimal: ...
    @property
    def state_tax(self) -> Decimal: ...
    @property
    def early_withdrawal_penalty(self) -> Decimal: ...
    @property
    def gross_income(self) -> Decimal: ...
    @property
    def required_distributions(self) -> Decimal: ...
    @property
    def expenses(self) -> Decimal: ...
    @property
    def roth_conversions(self) -> Decimal: ...
    @property
    def medicare_irmaa(self) -> Decimal: ...


class _BalanceLike(Protocol):
    @property
    def account_id(self) -> str: ...
    @property
    def year(self) -> int: ...
    @property
    def ending_balance(self) -> Decimal: ...


def compute_summary(
    years: Sequence[_YearLike],
    account_balances: Sequence[_BalanceLike],
    illiquid_account_ids: set[str],
) -> ProjectionSummary | None:
    """Derive headline metrics from a completed projection.

    "Out of savings" = the first year liquid (investable) account balances are fully depleted, which
    mirrors Boldin's out-of-savings age. Estate value is net worth in the final modeled year.
    """
    if not years:
        return None
    liquid_by_year: dict[int, Decimal] = {}
    for bal in account_balances:
        if bal.account_id in illiquid_account_ids:
            continue
        liquid_by_year[bal.year] = liquid_by_year.get(bal.year, ZERO) + bal.ending_balance

    out_year: int | None = None
    out_age: int | None = None
    for row in years:
        if liquid_by_year.get(row.year, ZERO) <= ZERO:
            out_year = row.year
            out_age = row.age_primary
            break

    peak = max(years, key=lambda r: r.ending_net_worth)
    final = years[-1]
    return ProjectionSummary(
        final_year=final.year,
        final_age=final.age_primary,
        estate_net_worth=final.ending_net_worth,
        peak_net_worth=peak.ending_net_worth,
        peak_net_worth_year=peak.year,
        lifetime_federal_tax=quantize_cents(sum((r.federal_tax for r in years), ZERO)),
        lifetime_state_tax=quantize_cents(sum((r.state_tax for r in years), ZERO)),
        lifetime_penalties=quantize_cents(sum((r.early_withdrawal_penalty for r in years), ZERO)),
        lifetime_total_tax=quantize_cents(
            sum(
                (r.federal_tax + r.state_tax + r.early_withdrawal_penalty for r in years),
                ZERO,
            )
        ),
        total_lifetime_income=quantize_cents(
            sum((r.gross_income + r.required_distributions for r in years), ZERO)
        ),
        total_lifetime_expenses=quantize_cents(sum((r.expenses for r in years), ZERO)),
        total_lifetime_roth_conversions=quantize_cents(
            sum((r.roth_conversions for r in years), ZERO)
        ),
        total_lifetime_irmaa=quantize_cents(sum((r.medicare_irmaa for r in years), ZERO)),
        out_of_savings_year=out_year,
        out_of_savings_age=out_age,
    )


@dataclass(frozen=True)
class _IncomeBuckets:
    gross: Decimal = ZERO
    wages: Decimal = ZERO
    pensions_taxable_federal: Decimal = ZERO
    pensions_taxable_state: Decimal = ZERO
    annuity_taxable: Decimal = ZERO
    ss_gross: Decimal = ZERO
    ltcg: Decimal = ZERO


@dataclass(frozen=True)
class _ContributionResult:
    employee_total: Decimal = ZERO
    employer_total: Decimal = ZERO
    federal_wage_reduction: Decimal = ZERO
    state_wage_reduction: Decimal = ZERO


def quantize_cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _apply_contributions(
    scenario: ScenarioInput,
    accounts: dict[str, AccountYearState],
    contributions: dict[str, Decimal],
    income: _IncomeBuckets,
    expenses: Decimal,
    year: int,
) -> _ContributionResult:
    """Apply employee + employer contributions for the year.

    Employee contributions are funded from current-year income (capped at ``income - expenses``
    so the engine never withdraws from savings just to fund a contribution). Employer match scales
    with the funded fraction of the employee contribution. Returns totals + taxable-wage reductions.
    """
    active = [
        plan
        for plan in scenario.contribution_plans
        if _stream_active(plan.start_year, plan.end_year, year)
    ]
    if not active:
        return _ContributionResult()

    intended: list[tuple[ContributionPlan, Decimal, Decimal]] = []
    intended_employee_total = ZERO
    for plan in active:
        rate = _contribution_inflation_rate(plan, scenario.assumptions)
        employee = _inflate(plan.annual_amount, rate, year - plan.start_year)
        employer = _inflate(plan.employer_match_amount, rate, year - plan.start_year)
        intended.append((plan, employee, employer))
        intended_employee_total += employee

    available = max(ZERO, income.gross - expenses)
    fund_fraction = ONE
    if intended_employee_total > available and intended_employee_total > ZERO:
        fund_fraction = available / intended_employee_total

    employee_total = ZERO
    employer_total = ZERO
    federal_reduction = ZERO
    state_reduction = ZERO
    for plan, employee, employer in intended:
        funded_employee = quantize_cents(employee * fund_fraction)
        funded_employer = quantize_cents(employer * fund_fraction)
        account = accounts.get(plan.account_id)
        if account is None:
            continue
        total_in = funded_employee + funded_employer
        account.balance += total_in
        contributions[plan.account_id] += total_in
        if account.account_type in ROTH_ACCOUNT_TYPES:
            account.roth_contributions_basis += funded_employee
        employee_total += funded_employee
        employer_total += funded_employer
        if account.account_type in FEDERAL_PRETAX_ACCOUNT_TYPES:
            federal_reduction += funded_employee
        if account.account_type in STATE_PRETAX_ACCOUNT_TYPES:
            state_reduction += funded_employee

    return _ContributionResult(
        employee_total=quantize_cents(employee_total),
        employer_total=quantize_cents(employer_total),
        federal_wage_reduction=quantize_cents(federal_reduction),
        state_wage_reduction=quantize_cents(state_reduction),
    )


def _service_debt(
    accounts: dict[str, AccountYearState],
    distributions: dict[str, Decimal],
) -> Decimal:
    """Pay scheduled principal on debt accounts. Interest accrues via the end-of-year return loop.

    The payment is a cash outflow (folded into the year's funding need). Principal cannot go below
    zero, so the loan stops drawing payments once paid off.
    """
    total = ZERO
    for account in accounts.values():
        if account.account_type != "debt" or account.debt_annual_payment <= ZERO:
            continue
        payment = quantize_cents(min(account.debt_annual_payment, account.balance))
        if payment <= ZERO:
            continue
        account.balance -= payment
        distributions[account.id] += payment
        total += payment
    return quantize_cents(total)


def _net_worth(accounts: dict[str, AccountYearState]) -> Decimal:
    """Total net worth: assets minus debt liabilities (debt balances are amounts owed)."""
    total = ZERO
    for account in accounts.values():
        if account.account_type == "debt":
            total -= account.balance
        else:
            total += account.balance
    return quantize_cents(total)


def _contribution_inflation_rate(plan: ContributionPlan, assumptions: AssumptionSet) -> Decimal:
    if plan.inflation_kind == "custom":
        return plan.custom_inflation_rate or ZERO
    if plan.inflation_kind == "none":
        return ZERO
    return assumptions.cpi_rate


def run_projection(
    scenario: ScenarioInput,
    irs_data_version: str,
    engine_version: str,
) -> ProjectionRun:
    people = {person.id: person for person in scenario.people}
    accounts = {account.id: _clone_account(account) for account in scenario.accounts}
    projection_years: list[ProjectionYear] = []
    account_balances: list[ProjectionAccountBalance] = []
    warnings: list[ProjectionWarning] = []
    convergence_log: list[dict[str, str | int]] = []
    magi_history: dict[int, Decimal] = {}

    for year in range(scenario.start_year, scenario.end_year + 1):
        beginning = {account_id: account.balance for account_id, account in accounts.items()}
        contributions = {account_id: ZERO for account_id in accounts}
        distributions = {account_id: ZERO for account_id in accounts}
        rmd_base_accounts = _clone_accounts(accounts)

        income = _income_for_year(scenario.income_streams, scenario.assumptions, year, people)
        expenses = _expenses_for_year(scenario.expense_streams, scenario.assumptions, year)
        sepp_locked = _active_sepp_account_ids(scenario.sepp_plans, year)
        sepp_distributions = _take_sepp_distributions(
            scenario,
            accounts,
            distributions,
            year,
            warnings,
        )
        rmd_distributions = _take_rmds(
            rmd_base_accounts,
            accounts,
            scenario.people,
            irs_data_version,
            year,
            distributions,
            warnings,
            scenario.id,
        )
        roth_conversions = _execute_roth_conversions(
            scenario,
            accounts,
            year,
            warnings,
        )
        contribution = _apply_contributions(
            scenario, accounts, contributions, income, expenses, year
        )
        debt_payments = _service_debt(accounts, distributions)
        medicare_enrolled = sum(
            1 for person in scenario.people if person.age_in_year(year) >= 65
        )
        irmaa = irmaa_annual_surcharge(
            magi_history.get(year - 2, ZERO),
            scenario.filing_status,
            medicare_enrolled,
            year,
            irs_data_version,
            scenario.assumptions.bracket_indexing_rate,
        )
        cash_need = quantize_cents(
            expenses + contribution.employee_total + debt_payments + irmaa
        )

        pre_flexible_accounts = _clone_accounts(accounts)
        final_accounts, flex, tax_result, converged, iterations = _solve_flexible_withdrawals(
            scenario,
            pre_flexible_accounts,
            income,
            cash_need,
            sepp_distributions,
            rmd_distributions,
            roth_conversions,
            sepp_locked,
            people,
            year,
            irs_data_version,
            contribution,
        )
        accounts = final_accounts
        _add_withdrawal_distributions(distributions, flex)
        magi_history[year] = tax_result.magi
        if irmaa > ZERO:
            warnings.append(
                ProjectionWarning(
                    str(uuid4()),
                    scenario.id,
                    year,
                    "info",
                    "irmaa_threshold_crossed",
                    f"Medicare IRMAA surcharge of {irmaa} applies "
                    f"(based on MAGI from {year - 2}).",
                )
            )

        final_tax = _total_tax(tax_result)
        surplus = quantize_cents(
            income.gross + sepp_distributions + rmd_distributions - cash_need - final_tax
        )
        if surplus > ZERO:
            _route_surplus(scenario, accounts, contributions, surplus, expenses)
        if not converged:
            warnings.append(
                ProjectionWarning(
                    str(uuid4()),
                    scenario.id,
                    year,
                    "warning",
                    "projection_tax_convergence_max",
                    "Tax iteration reached the configured maximum; conservative result used.",
                )
            )
        funding_gap = quantize_cents(
            cash_need + final_tax - income.gross - sepp_distributions - rmd_distributions
        )
        if funding_gap > flex.withdrawn + scenario.assumptions.tax_iteration_tolerance:
            warnings.append(
                ProjectionWarning(
                    str(uuid4()),
                    scenario.id,
                    year,
                    "error",
                    "projection_funding_gap_unfunded",
                    "Flexible withdrawals could not fully fund expenses and taxes.",
                )
            )
        convergence_log.append(
            {"year": year, "iterations": iterations, "converged": "true" if converged else "false"}
        )

        for account_id, account in accounts.items():
            pre_return = account.balance
            rate = scenario.return_overrides.get(account_id, {}).get(year, account.expected_return)
            investment_return = quantize_cents(pre_return * rate)
            account.balance = quantize_cents(account.balance + investment_return)
            account_balances.append(
                ProjectionAccountBalance(
                    id=str(uuid4()),
                    scenario_id=scenario.id,
                    year=year,
                    account_id=account_id,
                    beginning_balance=quantize_cents(beginning[account_id]),
                    contributions=quantize_cents(contributions[account_id]),
                    distributions=quantize_cents(distributions[account_id]),
                    investment_return=investment_return,
                    ending_balance=account.balance,
                )
            )

        primary = people[scenario.primary_person_id]
        spouse_age = (
            None
            if scenario.spouse_person_id is None
            else people[scenario.spouse_person_id].age_in_year(year)
        )
        projection_years.append(
            ProjectionYear(
                id=str(uuid4()),
                scenario_id=scenario.id,
                year=year,
                age_primary=primary.age_in_year(year),
                age_spouse=spouse_age,
                gross_income=income.gross,
                required_distributions=quantize_cents(sepp_distributions + rmd_distributions),
                flexible_withdrawals=flex.withdrawn,
                roth_conversions=roth_conversions,
                expenses=expenses,
                federal_tax=tax_result.federal_tax,
                state_tax=tax_result.state_tax,
                early_withdrawal_penalty=quantize_cents(
                    tax_result.early_withdrawal_penalty + tax_result.hsa_penalty
                ),
                magi=tax_result.magi,
                provisional_income=tax_result.provisional_income,
                ss_taxable_portion=tax_result.ss_taxable_portion,
                ordinary_taxable_income=tax_result.ordinary_taxable,
                medicare_irmaa=irmaa,
                surplus=max(surplus, ZERO),
                ending_net_worth=_net_worth(accounts),
            )
        )

    metadata = ProjectionRunMetadata(
        id=str(uuid4()),
        scenario_id=scenario.id,
        run_at=datetime.now(UTC).isoformat(),
        engine_version=engine_version,
        irs_data_version=irs_data_version,
        assumption_snapshot=_assumption_snapshot(scenario.assumptions),
        convergence_log=convergence_log,
    )
    illiquid_ids = {
        account_id
        for account_id, account in accounts.items()
        if account.account_type in ILLIQUID_ACCOUNT_TYPES
    }
    summary = compute_summary(projection_years, account_balances, illiquid_ids)
    assert summary is not None or not projection_years
    return ProjectionRun(
        metadata,
        projection_years,
        account_balances,
        warnings,
        summary
        or ProjectionSummary(
            final_year=scenario.start_year,
            final_age=0,
            estate_net_worth=ZERO,
            peak_net_worth=ZERO,
            peak_net_worth_year=scenario.start_year,
            lifetime_federal_tax=ZERO,
            lifetime_state_tax=ZERO,
            lifetime_penalties=ZERO,
            lifetime_total_tax=ZERO,
            total_lifetime_income=ZERO,
            total_lifetime_expenses=ZERO,
            total_lifetime_roth_conversions=ZERO,
            total_lifetime_irmaa=ZERO,
            out_of_savings_year=None,
            out_of_savings_age=None,
        ),
    )


def _solve_flexible_withdrawals(
    scenario: ScenarioInput,
    pre_flexible_accounts: dict[str, AccountYearState],
    income: _IncomeBuckets,
    cash_need: Decimal,
    sepp_distributions: Decimal,
    rmd_distributions: Decimal,
    roth_conversions: Decimal,
    sepp_locked: set[str],
    people: dict[str, Person],
    year: int,
    irs_data_version: str,
    contribution: _ContributionResult,
) -> tuple[dict[str, AccountYearState], WithdrawalResult, TaxResult, bool, int]:
    prior_gap: Decimal | None = None
    best_accounts = _clone_accounts(pre_flexible_accounts)
    best_flex = _empty_withdrawal()
    best_tax = _compute_projection_taxes(
        scenario,
        income,
        sepp_distributions,
        rmd_distributions,
        roth_conversions,
        best_flex,
        year,
        irs_data_version,
        contribution,
    )

    for iteration in range(scenario.assumptions.tax_iteration_max + 1):
        total_tax = _total_tax(best_tax)
        gap = quantize_cents(
            cash_need + total_tax - income.gross - sepp_distributions - rmd_distributions
        )
        if gap <= ZERO:
            return (
                _clone_accounts(pre_flexible_accounts),
                _empty_withdrawal(),
                best_tax,
                True,
                iteration,
            )
        within_tolerance = (
            prior_gap is not None
            and abs(gap - prior_gap) <= scenario.assumptions.tax_iteration_tolerance
        )
        if within_tolerance:
            return best_accounts, best_flex, best_tax, True, iteration

        trial_accounts = _clone_accounts(pre_flexible_accounts)
        best_flex = execute_withdrawals(
            gap,
            trial_accounts,
            scenario.withdrawal_order,
            year,
            list(people.values()),
            sepp_locked,
        )
        best_accounts = trial_accounts
        best_tax = _compute_projection_taxes(
            scenario,
            income,
            sepp_distributions,
            rmd_distributions,
            roth_conversions,
            best_flex,
            year,
            irs_data_version,
            contribution,
        )
        prior_gap = gap

    return best_accounts, best_flex, best_tax, False, scenario.assumptions.tax_iteration_max


def _compute_projection_taxes(
    scenario: ScenarioInput,
    income: _IncomeBuckets,
    sepp_distributions: Decimal,
    rmd_distributions: Decimal,
    roth_conversions: Decimal,
    flex: WithdrawalResult,
    year: int,
    irs_data_version: str,
    contribution: _ContributionResult,
) -> TaxResult:
    wages_federal = max(ZERO, income.wages - contribution.federal_wage_reduction)
    wages_state = max(ZERO, income.wages - contribution.state_wage_reduction)
    return compute_taxes(
        TaxInput(
            year=year,
            filing_status=scenario.filing_status,
            state=scenario.state,
            ages={person.id: person.age_in_year(year) for person in scenario.people},
            wages=wages_federal,
            wages_state=wages_state,
            pensions_taxable_federal=income.pensions_taxable_federal,
            pensions_taxable_state=income.pensions_taxable_state,
            traditional_distributions=flex.ordinary_income,
            roth_conversions=roth_conversions,
            sepp_distributions=sepp_distributions,
            rmd_distributions=rmd_distributions,
            annuity_taxable=income.annuity_taxable,
            ltcg=income.ltcg + flex.ltcg,
            ss_gross=income.ss_gross,
            penalty_eligible_distributions=flex.penalty_eligible,
            hsa_penalty_eligible_distributions=flex.hsa_penalty_eligible,
            irs_data_version=irs_data_version,
        )
    )


def _income_for_year(
    streams: list[IncomeStream],
    assumptions: AssumptionSet,
    year: int,
    people: dict[str, Person],
) -> _IncomeBuckets:
    gross = wages = pensions_federal = pensions_state = annuity = ss = ltcg = ZERO
    for stream in streams:
        if not _stream_active(stream.start_year, stream.end_year, year):
            continue
        if stream.kind == "social_security" and stream.claiming_age is not None:
            person = people.get(stream.person_id or "")
            if person is not None and person.age_in_year(year) < stream.claiming_age:
                continue
        amount = _inflate(
            stream.annual_amount,
            _income_inflation_rate(stream, assumptions),
            year - stream.start_year,
        )
        gross += amount
        if stream.kind == "social_security":
            ss += amount
        elif stream.kind == "pension":
            if stream.is_taxable_federal:
                pensions_federal += amount
            if stream.is_taxable_state:
                pensions_state += amount
        elif stream.kind == "annuity":
            if stream.is_taxable_federal:
                annuity += amount
        elif stream.kind == "passive":
            ltcg += amount if stream.is_taxable_federal else ZERO
        elif stream.is_taxable_federal:
            wages += amount
    return _IncomeBuckets(
        quantize_cents(gross),
        quantize_cents(wages),
        quantize_cents(pensions_federal),
        quantize_cents(pensions_state),
        quantize_cents(annuity),
        quantize_cents(ss),
        quantize_cents(ltcg),
    )


def _expenses_for_year(
    streams: list[ExpenseStream],
    assumptions: AssumptionSet,
    year: int,
) -> Decimal:
    total = ZERO
    for stream in streams:
        if _stream_active(stream.start_year, stream.end_year, year):
            total += _inflate(
                stream.annual_amount,
                _expense_inflation_rate(stream, assumptions),
                year - stream.start_year,
            )
    return quantize_cents(total)


def _stream_active(start_year: int, end_year: int | None, year: int) -> bool:
    return start_year <= year and (end_year is None or year <= end_year)


def _income_inflation_rate(stream: IncomeStream, assumptions: AssumptionSet) -> Decimal:
    if stream.inflation_kind == "ss_cola":
        return assumptions.ss_cola_rate
    if stream.inflation_kind == "pension_cola":
        return assumptions.pension_cola_rate
    if stream.inflation_kind == "custom":
        return stream.custom_inflation_rate or ZERO
    if stream.inflation_kind == "none":
        return ZERO
    return assumptions.cpi_rate


def _expense_inflation_rate(stream: ExpenseStream, assumptions: AssumptionSet) -> Decimal:
    if stream.inflation_kind == "healthcare":
        return assumptions.healthcare_inflation_rate
    if stream.inflation_kind == "custom":
        return stream.custom_inflation_rate or ZERO
    if stream.inflation_kind == "none":
        return ZERO
    return assumptions.cpi_rate


def _inflate(amount: Decimal, rate: Decimal, years: int) -> Decimal:
    return quantize_cents(amount * ((ONE + rate) ** years))


def _active_sepp_account_ids(plans: list[SeppProjectionPlan], year: int) -> set[str]:
    return {
        plan.account_id
        for plan in plans
        if plan.status == "active" and plan.start_year <= year <= plan.required_end_year
    }


def _take_sepp_distributions(
    scenario: ScenarioInput,
    accounts: dict[str, AccountYearState],
    distributions: dict[str, Decimal],
    year: int,
    warnings: list[ProjectionWarning],
) -> Decimal:
    total = ZERO
    for plan in scenario.sepp_plans:
        if plan.status != "active" or not (plan.start_year <= year <= plan.required_end_year):
            continue
        account = accounts[plan.account_id]
        amount = quantize_cents(min(account.balance, plan.annual_payment))
        account.balance -= amount
        distributions[account.id] += amount
        total += amount
        if amount < plan.annual_payment:
            warnings.append(
                ProjectionWarning(
                    str(uuid4()),
                    scenario.id,
                    year,
                    "error",
                    "projection_required_distribution_unfunded",
                    "Required SEPP distribution exceeds account balance.",
                )
            )
    return quantize_cents(total)


def _take_rmds(
    rmd_base_accounts: dict[str, AccountYearState],
    accounts: dict[str, AccountYearState],
    people: list[Person],
    irs_data_version: str,
    year: int,
    distributions: dict[str, Decimal],
    warnings: list[ProjectionWarning],
    scenario_id: str,
) -> Decimal:
    total = ZERO
    rmds = compute_rmd_for_year(year, list(rmd_base_accounts.values()), people, irs_data_version)
    for account_id, rmd in rmds.items():
        account = accounts[account_id]
        amount = quantize_cents(min(account.balance, rmd))
        account.balance -= amount
        distributions[account_id] += amount
        total += amount
        if amount < rmd:
            warnings.append(
                ProjectionWarning(
                    str(uuid4()),
                    scenario_id,
                    year,
                    "error",
                    "projection_required_distribution_unfunded",
                    "Required RMD exceeds account balance.",
                )
            )
    return quantize_cents(total)


def _execute_roth_conversions(
    scenario: ScenarioInput,
    accounts: dict[str, AccountYearState],
    year: int,
    warnings: list[ProjectionWarning],
) -> Decimal:
    total = ZERO
    for plan in scenario.roth_conversion_plans:
        if plan.year != year:
            continue
        result = execute_roth_conversion(plan, accounts)
        total += result.roth_conversions_taxable
        for issue in result.issues:
            warnings.append(
                ProjectionWarning(
                    str(uuid4()),
                    scenario.id,
                    year,
                    issue.severity,
                    issue.code,
                    issue.message,
                )
            )
    return quantize_cents(total)


def _route_surplus(
    scenario: ScenarioInput,
    accounts: dict[str, AccountYearState],
    contributions: dict[str, Decimal],
    surplus: Decimal,
    expenses: Decimal,
) -> None:
    remaining = surplus
    cash = next((account for account in accounts.values() if account.account_type == "cash"), None)
    if cash is not None:
        reserve_target = quantize_cents(
            expenses * Decimal(scenario.assumptions.cash_reserve_target_months) / Decimal("12")
        )
        cash_top_up = quantize_cents(min(max(reserve_target - cash.balance, ZERO), remaining))
        cash.balance += cash_top_up
        contributions[cash.id] += cash_top_up
        remaining -= cash_top_up
    if remaining <= ZERO:
        return
    target = accounts.get(scenario.surplus_target_account_id or "")
    if target is None:
        target = next(
            (
                account
                for account in accounts.values()
                if account.account_type == "taxable_brokerage"
            ),
            cash,
        )
    if target is not None:
        target.balance += remaining
        contributions[target.id] += remaining


def _add_withdrawal_distributions(
    distributions: dict[str, Decimal],
    withdrawal: WithdrawalResult,
) -> None:
    for line in withdrawal.lines:
        distributions[line.account_id] += line.amount


def _total_tax(result: TaxResult) -> Decimal:
    return quantize_cents(
        result.federal_tax + result.state_tax + result.early_withdrawal_penalty + result.hsa_penalty
    )


def _empty_withdrawal() -> WithdrawalResult:
    return WithdrawalResult(ZERO, ZERO, ZERO, ZERO, ZERO, ZERO, [])


def _clone_accounts(accounts: dict[str, AccountYearState]) -> dict[str, AccountYearState]:
    return {account_id: _clone_account(account) for account_id, account in accounts.items()}


def _clone_account(account: AccountYearState) -> AccountYearState:
    return AccountYearState(
        id=account.id,
        owner_person_id=account.owner_person_id,
        account_type=account.account_type,
        balance=account.balance,
        expected_return=account.expected_return,
        return_stddev=account.return_stddev,
        cost_basis_pct=account.cost_basis_pct,
        roth_first_contribution_year=account.roth_first_contribution_year,
        roth_contributions_basis=account.roth_contributions_basis,
        roth_earnings_balance=account.roth_earnings_balance,
        roth_conversion_lots=[
            RothConversionLotState(lot.conversion_year, lot.amount, lot.taxable_conversion)
            for lot in account.roth_conversion_lots
        ],
        hsa_qualified_medical_expense_pct=account.hsa_qualified_medical_expense_pct,
        spouse_beneficiary_person_id=account.spouse_beneficiary_person_id,
        spouse_is_sole_beneficiary=account.spouse_is_sole_beneficiary,
        debt_annual_payment=account.debt_annual_payment,
        exclude_from_withdrawals=account.exclude_from_withdrawals,
    )


def _assumption_snapshot(assumptions: AssumptionSet) -> dict[str, str | int]:
    return {
        "cpi_rate": str(assumptions.cpi_rate),
        "healthcare_inflation_rate": str(assumptions.healthcare_inflation_rate),
        "ss_cola_rate": str(assumptions.ss_cola_rate),
        "pension_cola_rate": str(assumptions.pension_cola_rate),
        "cash_reserve_target_months": assumptions.cash_reserve_target_months,
        "tax_iteration_max": assumptions.tax_iteration_max,
        "tax_iteration_tolerance": str(assumptions.tax_iteration_tolerance),
    }
