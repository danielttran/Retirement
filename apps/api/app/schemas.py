from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FilingStatus = Literal["single", "mfj", "mfs", "hoh", "qw"]
AccountType = Literal[
    "cash",
    "taxable_brokerage",
    "traditional_ira",
    "traditional_401k",
    "traditional_403b",
    "roth_ira",
    "roth_401k",
    "hsa",
    "governmental_457b",
    "real_estate",
    "debt",
    "529",
    "deferred_comp",
    "life_insurance",
]
IncomeKind = Literal[
    "salary", "pension", "social_security", "annuity", "passive", "windfall", "other"
]
IncomeInflationKind = Literal["cpi", "ss_cola", "pension_cola", "none", "custom"]
ExpenseKind = Literal["must_spend", "discretionary", "healthcare", "one_time"]
ExpenseInflationKind = Literal["cpi", "healthcare", "none", "custom"]
SeppMethod = Literal["rmd", "fixed_amortization", "fixed_annuitization"]
SeppStatus = Literal["planned", "active", "completed", "modified", "cancelled"]
WarningSeverity = Literal["info", "warning", "error"]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PersonCreate(BaseModel):
    name: str = Field(min_length=1)
    dob: str
    retirement_date: str | None = None
    life_expectancy_age: int = Field(default=95, ge=1, le=130)


class PersonRead(PersonCreate, ApiModel):
    id: str
    household_id: str
    is_primary: bool


class HouseholdCreate(BaseModel):
    name: str = Field(min_length=1)
    filing_status: FilingStatus = "single"
    state: str = "MA"
    primary_person: PersonCreate
    scenario_name: str = "Baseline"


class HouseholdRead(ApiModel):
    id: str
    name: str
    filing_status: str
    state: str
    created_at: str
    people: list[PersonRead]


class AccountCreate(BaseModel):
    owner_person_id: str
    name: str = Field(min_length=1)
    account_type: AccountType
    current_balance: Decimal = Field(ge=Decimal("-999999999999"))
    expected_return: Decimal = Field(default=Decimal("0.05"))
    return_stddev: Decimal | None = None
    cost_basis_pct: Decimal | None = None
    roth_first_contribution_year: int | None = None
    is_governmental_457b: bool = False
    has_rollover_basis_from_penalty_account: bool = False
    rollover_basis_pct: Decimal | None = None
    hsa_qualified_medical_expense_pct: Decimal | None = None
    debt_annual_payment: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    exclude_from_withdrawals: bool = False


class AccountRead(AccountCreate, ApiModel):
    id: str
    household_id: str
    notes: str | None
    created_at: str


class RothBasisRead(ApiModel):
    account_id: str
    contributions_basis: Decimal
    conversions_basis: Decimal
    earnings_balance: Decimal


class RothConversionLotRead(ApiModel):
    id: str
    account_id: str
    conversion_year: int
    converted_amount: Decimal
    notes: str | None


class IncomeStreamRead(ApiModel):
    id: str
    household_id: str
    person_id: str | None
    name: str
    kind: IncomeKind
    annual_amount: Decimal
    start_year: int
    end_year: int | None
    inflation_kind: IncomeInflationKind
    custom_inflation_rate: Decimal | None
    is_taxable_federal: bool
    is_taxable_state: bool
    claiming_age: int | None


class IncomeStreamCreate(BaseModel):
    person_id: str | None = None
    name: str = Field(min_length=1)
    kind: IncomeKind
    annual_amount: Decimal
    start_year: int
    end_year: int | None = None
    inflation_kind: IncomeInflationKind = "cpi"
    custom_inflation_rate: Decimal | None = None
    is_taxable_federal: bool = True
    is_taxable_state: bool = True
    claiming_age: int | None = None


class ExpenseStreamRead(ApiModel):
    id: str
    household_id: str
    name: str
    kind: ExpenseKind
    annual_amount: Decimal
    start_year: int
    end_year: int | None
    inflation_kind: ExpenseInflationKind
    custom_inflation_rate: Decimal | None


class ExpenseStreamCreate(BaseModel):
    name: str = Field(min_length=1)
    kind: ExpenseKind
    annual_amount: Decimal
    start_year: int
    end_year: int | None = None
    inflation_kind: ExpenseInflationKind = "cpi"
    custom_inflation_rate: Decimal | None = None


class ScenarioRead(ApiModel):
    id: str
    household_id: str
    name: str
    parent_scenario_id: str | None
    created_at: str


class AssumptionSetRead(ApiModel):
    id: str
    scenario_id: str
    cpi_rate: Decimal
    healthcare_inflation_rate: Decimal
    ss_cola_rate: Decimal
    pension_cola_rate: Decimal
    bracket_indexing_rate: Decimal
    itemized_deductions: Decimal
    cash_reserve_target_months: int
    irs_data_version: str
    engine_version: str
    state: str
    tax_iteration_max: int
    tax_iteration_tolerance: Decimal


class AssumptionSetUpdate(BaseModel):
    cpi_rate: Decimal = Decimal("0.025")
    healthcare_inflation_rate: Decimal = Decimal("0.04")
    ss_cola_rate: Decimal = Decimal("0.025")
    pension_cola_rate: Decimal = Decimal("0")
    bracket_indexing_rate: Decimal = Decimal("0.025")
    itemized_deductions: Decimal = Decimal("0")
    cash_reserve_target_months: int = 24
    irs_data_version: str = "2024-33"
    engine_version: str = "0.1.0"
    state: str = "MA"
    tax_iteration_max: int = 5
    tax_iteration_tolerance: Decimal = Decimal("1.00")


class WithdrawalStrategyRead(ApiModel):
    id: str
    scenario_id: str
    order_json: str
    surplus_target: str


class WithdrawalStrategyUpdate(BaseModel):
    order_json: str
    surplus_target: str = "taxable_brokerage"


class SeppPlanRead(ApiModel):
    id: str
    scenario_id: str
    account_id: str
    method: SeppMethod
    status: SeppStatus
    valuation_date: str
    first_payment_date: str
    required_end_date: str
    age_at_first_payment: Decimal
    account_balance_at_valuation: Decimal
    afr_prior_month: Decimal | None
    afr_two_months_prior: Decimal | None
    afr_month_used: str | None
    selected_interest_rate: Decimal | None
    max_allowed_interest_rate: Decimal | None
    initial_life_expectancy_factor: Decimal | None
    initial_annual_payment_locked: Decimal | None
    irs_notice_version: str
    mortality_table_version: str | None
    beneficiary_dob_snapshot: str | None
    calculation_log_json: str | None
    has_switched_to_rmd: bool
    switched_to_rmd_year: int | None


class SeppPlanCreate(BaseModel):
    account_id: str
    method: SeppMethod
    status: SeppStatus = "active"
    valuation_date: str
    first_payment_date: str
    required_end_date: str
    age_at_first_payment: Decimal
    account_balance_at_valuation: Decimal
    afr_prior_month: Decimal | None = None
    afr_two_months_prior: Decimal | None = None
    afr_month_used: str | None = None
    selected_interest_rate: Decimal | None = None
    max_allowed_interest_rate: Decimal | None = None
    initial_life_expectancy_factor: Decimal | None = None
    initial_annual_payment_locked: Decimal | None = None
    irs_notice_version: str = "Notice 2022-6"
    mortality_table_version: str | None = None
    beneficiary_dob_snapshot: str | None = None
    calculation_log_json: str | None = None
    has_switched_to_rmd: bool = False
    switched_to_rmd_year: int | None = None


class RothConversionPlanRead(ApiModel):
    id: str
    scenario_id: str
    source_account_id: str
    destination_account_id: str
    year: int
    amount: Decimal
    tax_payment_source_account_id: str | None


class RothConversionPlanCreate(BaseModel):
    source_account_id: str
    destination_account_id: str
    year: int
    amount: Decimal
    tax_payment_source_account_id: str | None = None


ContributionInflationKind = Literal["cpi", "none", "custom"]


class ContributionCreate(BaseModel):
    account_id: str
    annual_amount: Decimal = Field(ge=Decimal("0"))
    start_year: int
    end_year: int | None = None
    inflation_kind: ContributionInflationKind = "cpi"
    custom_inflation_rate: Decimal | None = None
    employer_match_amount: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))


class ContributionRead(ApiModel):
    id: str
    scenario_id: str
    account_id: str
    annual_amount: Decimal
    start_year: int
    end_year: int | None
    inflation_kind: str
    custom_inflation_rate: Decimal | None
    employer_match_amount: Decimal


class ProjectionRunMetadataRead(ApiModel):
    id: str
    scenario_id: str
    run_at: str
    engine_version: str
    irs_data_version: str
    assumption_snapshot_json: str
    convergence_log_json: str | None


class ProjectionYearRead(ApiModel):
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
    ordinary_taxable_income: Decimal = Decimal("0")
    medicare_irmaa: Decimal = Decimal("0")
    surplus: Decimal
    ending_net_worth: Decimal


class ProjectionAccountBalanceRead(ApiModel):
    id: str
    scenario_id: str
    year: int
    account_id: str
    beginning_balance: Decimal
    contributions: Decimal
    distributions: Decimal
    investment_return: Decimal
    ending_balance: Decimal


class ProjectionWarningRead(ApiModel):
    id: str
    scenario_id: str
    year: int | None
    severity: WarningSeverity
    code: str
    message: str


class ProjectionSummaryRead(BaseModel):
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
    total_lifetime_irmaa: Decimal = Decimal("0")
    out_of_savings_year: int | None
    out_of_savings_age: int | None


class ProjectionRead(ApiModel):
    metadata: ProjectionRunMetadataRead
    years: list[ProjectionYearRead]
    account_balances: list[ProjectionAccountBalanceRead]
    warnings: list[ProjectionWarningRead]
    summary: ProjectionSummaryRead | None = None


class ClaimingOptionRead(BaseModel):
    claiming_age: int
    monthly_benefit: Decimal
    annual_benefit: Decimal
    lifetime_total: Decimal
    break_even_age_vs_earliest: int | None


class SocialSecurityExplorerRead(BaseModel):
    person_id: str
    person_name: str
    pia_annual: Decimal
    full_retirement_age_months: int
    current_claiming_age: int | None
    options: list[ClaimingOptionRead]
    max_lifetime_claiming_age: int


class ConversionSuggestionRead(BaseModel):
    year: int
    amount: Decimal
    ordinary_taxable_income: Decimal
    magi: Decimal
    headroom: Decimal
    traditional_balance: Decimal


class RothExplorerRead(BaseModel):
    strategy: str
    source_account_id: str | None
    destination_account_id: str | None
    suggestions: list[ConversionSuggestionRead]
    total_converted: Decimal
    baseline_lifetime_tax: Decimal
    projected_lifetime_tax: Decimal
    baseline_estate: Decimal
    projected_estate: Decimal
    note: str | None = None


class ScoreComponentRead(BaseModel):
    label: str
    score: int
    weight: int
    detail: str


class AlertRead(BaseModel):
    severity: str
    title: str
    message: str


class InsightsRead(BaseModel):
    score: int
    rating: str
    components: list[ScoreComponentRead]
    alerts: list[AlertRead]


class MonteCarloRead(BaseModel):
    trials: int
    success_count: int
    chance_of_success: Decimal
    p10_estate: Decimal
    p50_estate: Decimal
    p90_estate: Decimal
    median_out_of_savings_age: int | None


class ScenarioDetail(ScenarioRead):
    household: HouseholdRead
    accounts: list[AccountRead]
    total_account_balance: Decimal
