export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export type Person = {
  id: string;
  household_id: string;
  name: string;
  dob: string;
  retirement_date: string | null;
  life_expectancy_age: number;
  is_primary: boolean;
};

export type Household = {
  id: string;
  name: string;
  filing_status: string;
  state: string;
  created_at: string;
  people: Person[];
};

export type Scenario = {
  id: string;
  household_id: string;
  name: string;
  parent_scenario_id: string | null;
  created_at: string;
};

export type Account = {
  id: string;
  household_id: string;
  owner_person_id: string;
  name: string;
  account_type: string;
  current_balance: string;
  expected_return: string;
  cost_basis_pct: string | null;
  roth_first_contribution_year: number | null;
  debt_annual_payment: string;
  exclude_from_withdrawals: boolean;
  sale_year: number | null;
  selling_cost_pct: string;
  created_at: string;
};

export type ScenarioDetail = Scenario & {
  household: Household;
  accounts: Account[];
  total_account_balance: string;
};

export type IncomeStream = {
  id: string;
  household_id: string;
  person_id: string | null;
  name: string;
  kind: string;
  annual_amount: string;
  start_year: number;
  end_year: number | null;
  inflation_kind: string;
  custom_inflation_rate: string | null;
  is_taxable_federal: boolean;
  is_taxable_state: boolean;
  claiming_age: number | null;
};

export type ExpenseStream = {
  id: string;
  household_id: string;
  name: string;
  kind: string;
  annual_amount: string;
  start_year: number;
  end_year: number | null;
  inflation_kind: string;
  custom_inflation_rate: string | null;
};

export type AssumptionSet = {
  id: string;
  scenario_id: string;
  cpi_rate: string;
  healthcare_inflation_rate: string;
  ss_cola_rate: string;
  pension_cola_rate: string;
  housing_appreciation_rate: string;
  bracket_indexing_rate: string;
  itemized_deductions: string;
  cash_reserve_target_months: number;
  irs_data_version: string;
  engine_version: string;
  state: string;
  tax_iteration_max: number;
  tax_iteration_tolerance: string;
};

export type WithdrawalStrategy = {
  id: string;
  scenario_id: string;
  order_json: string;
  surplus_target: string;
};

export type SeppPlan = {
  id: string;
  scenario_id: string;
  account_id: string;
  method: string;
  status: string;
  valuation_date: string;
  first_payment_date: string;
  required_end_date: string;
  age_at_first_payment: string;
  account_balance_at_valuation: string;
  afr_prior_month: string | null;
  afr_two_months_prior: string | null;
  afr_month_used: string | null;
  selected_interest_rate: string | null;
  max_allowed_interest_rate: string | null;
  initial_life_expectancy_factor: string | null;
  initial_annual_payment_locked: string | null;
  irs_notice_version: string;
  mortality_table_version: string | null;
  beneficiary_dob_snapshot: string | null;
  calculation_log_json: string | null;
  has_switched_to_rmd: boolean;
  switched_to_rmd_year: number | null;
};

export type Contribution = {
  id: string;
  scenario_id: string;
  account_id: string;
  annual_amount: string;
  start_year: number;
  end_year: number | null;
  inflation_kind: string;
  custom_inflation_rate: string | null;
  employer_match_amount: string;
};

export type RothConversionPlan = {
  id: string;
  scenario_id: string;
  source_account_id: string;
  destination_account_id: string;
  year: number;
  amount: string;
  tax_payment_source_account_id: string | null;
};

export type ProjectionYear = {
  id: string;
  scenario_id: string;
  year: number;
  age_primary: number;
  age_spouse: number | null;
  gross_income: string;
  required_distributions: string;
  flexible_withdrawals: string;
  roth_conversions: string;
  expenses: string;
  federal_tax: string;
  state_tax: string;
  early_withdrawal_penalty: string;
  magi: string;
  provisional_income: string;
  ss_taxable_portion: string;
  ordinary_taxable_income: string;
  medicare_irmaa: string;
  surplus: string;
  ending_net_worth: string;
};

export type ProjectionAccountBalance = {
  id: string;
  scenario_id: string;
  year: number;
  account_id: string;
  beginning_balance: string;
  contributions: string;
  distributions: string;
  investment_return: string;
  ending_balance: string;
};

export type ProjectionWarning = {
  id: string;
  scenario_id: string;
  year: number | null;
  severity: "info" | "warning" | "error";
  code: string;
  message: string;
};

export type ProjectionRunMetadata = {
  id: string;
  scenario_id: string;
  run_at: string;
  engine_version: string;
  irs_data_version: string;
  assumption_snapshot_json: string;
  convergence_log_json: string | null;
};

export type ProjectionSummary = {
  final_year: number;
  final_age: number;
  estate_net_worth: string;
  peak_net_worth: string;
  peak_net_worth_year: number;
  lifetime_federal_tax: string;
  lifetime_state_tax: string;
  lifetime_penalties: string;
  lifetime_total_tax: string;
  total_lifetime_income: string;
  total_lifetime_expenses: string;
  total_lifetime_roth_conversions: string;
  total_lifetime_irmaa: string;
  out_of_savings_year: number | null;
  out_of_savings_age: number | null;
};

export type ProjectionRun = {
  metadata: ProjectionRunMetadata;
  years: ProjectionYear[];
  account_balances: ProjectionAccountBalance[];
  warnings: ProjectionWarning[];
  summary: ProjectionSummary | null;
};

export type ConversionSuggestion = {
  year: number;
  amount: string;
  ordinary_taxable_income: string;
  magi: string;
  headroom: string;
  traditional_balance: string;
};

export type RothExplorerResult = {
  strategy: string;
  source_account_id: string | null;
  destination_account_id: string | null;
  suggestions: ConversionSuggestion[];
  total_converted: string;
  baseline_lifetime_tax: string;
  projected_lifetime_tax: string;
  baseline_estate: string;
  projected_estate: string;
  note: string | null;
};

export type ScoreComponent = {
  label: string;
  score: number;
  weight: number;
  detail: string;
};

export type InsightAlert = {
  severity: "success" | "info" | "warning" | "critical";
  title: string;
  message: string;
};

export type InsightsResult = {
  score: number;
  rating: string;
  components: ScoreComponent[];
  alerts: InsightAlert[];
};

export type ClaimingOption = {
  claiming_age: number;
  monthly_benefit: string;
  annual_benefit: string;
  lifetime_total: string;
  break_even_age_vs_earliest: number | null;
};

export type SocialSecurityExplorerResult = {
  person_id: string;
  person_name: string;
  pia_annual: string;
  full_retirement_age_months: number;
  current_claiming_age: number | null;
  options: ClaimingOption[];
  max_lifetime_claiming_age: number;
};

export type MonteCarloResult = {
  trials: number;
  success_count: number;
  chance_of_success: string;
  p10_estate: string;
  p50_estate: string;
  p90_estate: string;
  median_out_of_savings_age: number | null;
};

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers
    }
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export function deleteScenario(scenarioId: string): Promise<void> {
  return apiRequest<void>(`/scenarios/${scenarioId}`, { method: "DELETE" });
}

export function deleteHousehold(householdId: string): Promise<void> {
  return apiRequest<void>(`/households/${householdId}`, { method: "DELETE" });
}

export function formatMoney(value: string | number): string {
  const numericValue = typeof value === "number" ? value : Number(value);
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0
  }).format(numericValue);
}

export function formatPercent(value: string | number): string {
  const numericValue = typeof value === "number" ? value : Number(value);
  return new Intl.NumberFormat("en-US", {
    style: "percent",
    maximumFractionDigits: 2
  }).format(numericValue);
}

export function downloadCsv(filename: string, rows: Record<string, unknown>[]): void {
  if (rows.length === 0) return;
  const headers = Object.keys(rows[0]);
  const lines = [
    headers.join(","),
    ...rows.map((row) => headers.map((h) => String(row[h] ?? "")).join(","))
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
