# Personal Retirement Planner — Design Specification

**Status:** Authoritative build spec. Supersedes prior drafts.
**Audience:** Implementation agent. Self-contained — no external references required to build.
**Scope:** Local-first personal retirement projection engine with scenario comparison, 72(t)/SEPP modeling, tax-lite, and Roth conversion support.

---

## 1. Project Goal

Build a local-first personal retirement planning application that models long-term retirement readiness, annual cash flow, withdrawal strategies, taxes, account depletion, and early-retirement bridge income using 72(t) / SEPP distributions and Roth conversion ladders.

**Core question:** Given current assets, income, expenses, taxes, retirement age, account types, withdrawal strategy, SEPP plans, and Roth conversion plans — can I retire safely, and when?

This is a **deterministic projection engine with scenario comparison**. Monte Carlo, portfolio optimization, and bank linking are explicit non-goals.

---

## 2. Scope

### 2.1 MVP Features (P0 unless marked)

| Priority | Feature | Notes |
|---|---|---|
| P0 | Household profile | People, DOB, retirement date, life expectancy, filing status |
| P0 | Manual accounts | Cash, taxable brokerage, Traditional IRA, 401(k), Roth IRA, Roth 401(k), HSA, 403(b), governmental 457(b), real estate, debts |
| P0 | Income streams | Salary, pension (with optional COLA), Social Security (user-entered annual benefit at chosen claiming age), annuity, passive |
| P0 | Expense streams | Must-spend, discretionary, healthcare (separate inflation), one-time |
| P0 | Annual projection engine | Year-by-year through life expectancy, `Decimal` throughout, deterministic |
| P0 | Scenario system | Clone, edit, compare scenarios side-by-side |
| P0 | Withdrawal engine | Ordered withdrawals with SEPP account lockout and Roth 3-layer logic |
| P0 | 72(t) / SEPP support | RMD, fixed amortization, fixed annuitization (single-life MVP), with locked calculation snapshot |
| P0 | Roth conversion support | Per-conversion 5-year clock, tax cost in conversion year, contribution to ladder bridge income |
| P0 | Tax-lite engine | Federal (standard deduction, ordinary brackets, LTCG stacking, simplified SS taxation), Massachusetts state, 10% early-withdrawal penalty |
| P0 | RMD engine | Data-driven applicable-age table, versioned IRS Single Life and Uniform Lifetime tables |
| P0 | Inflation model | Per-stream rates (general CPI, healthcare, SS COLA, pension flag), bracket/deduction indexing |
| P1 | Charts | Net worth, account balances, cash flow, taxes, SEPP payments, MAGI vs. ACA thresholds |
| P1 | CSV export | Annual projection + per-account balances |
| P1 | Validation warnings | High-risk tax, projection, ACA cliff, IRMAA-adjacent warnings (informational only) |
| P1 | ACA MAGI output | Display MAGI by year and flag PTC cliff thresholds (no optimization) |

### 2.2 Non-Goals for MVP

Bank linking, AI chat assistant, mobile app, full tax filing engine, full Social Security optimizer (PIA from earnings record, WEP/GPO), portfolio optimizer, advisor marketplace, multi-user collaboration, real-time market sync, estate planning, Monte Carlo, NIIT, AMT, full capital-gain stacking edge cases, QBI, IRMAA optimization, advanced ACA PTC optimization, fixed-annuitization with beneficiary, multi-state tax (only MA in MVP).

### 2.3 Explicit Scope Decisions (locked)

- **Roth withdrawals** are modeled as three layers: contributions, conversions (per-conversion 5-year clock), earnings.
- **Roth conversions** are user-scheduled actions in a given year; tax cost paid from a user-designated source (default: cash account).
- **ACA** is output-only — display MAGI and flag thresholds; no automatic optimization.
- **Social Security** is user-entered as `annual_benefit_at_claiming_age` and `claiming_age`. No PIA derivation, no WEP/GPO. COLA applied per the inflation model.
- **State tax**: Massachusetts only in MVP. State engine is pluggable for future states.
- **Investment returns**: deterministic per-account expected return. Schema reserves a `return_stddev` field for future Monte Carlo but it is unused by the MVP engine.
- **Cash reserve default**: 24 months of must-spend expenses (configurable per assumption set).
- **Fixed annuitization**: single-life only in MVP. Plans with a designated beneficiary using fixed annuitization are rejected with ERROR.

---

## 3. Architecture

```
repo/
├── apps/
│   ├── web/                  # Next.js 14+ App Router, TypeScript, Tailwind, Recharts
│   └── api/                  # FastAPI, Pydantic v2, SQLAlchemy 2.x
├── packages/
│   ├── planner_engine/       # Pure Python. NO web, NO DB imports. Decimal everywhere.
│   │   ├── sepp/
│   │   ├── tax/
│   │   ├── rmd/
│   │   ├── withdrawal/
│   │   ├── roth/
│   │   ├── projection/
│   │   └── inflation/
│   └── irs_data/             # Versioned JSON tables (AFR, lifetime tables, brackets, etc.)
├── alembic/
├── tests/
└── docker-compose.yml
```

- **Frontend:** Next.js 14+ (App Router), TypeScript strict, Tailwind, Recharts.
- **Backend:** FastAPI, Pydantic v2, SQLAlchemy 2.x.
- **Database:** SQLite, Alembic migrations. All monetary columns `NUMERIC` with custom SQLAlchemy `Money` type that round-trips `Decimal` through TEXT to avoid float coercion.
- **Engine:** Pure Python package. `Decimal` for all money, rates, and factors. `getcontext().prec = 28`. CI enforces an AST scan that fails the build if `float` literals or `float()` casts appear in `planner_engine/`.
- **Deployment:** Local Docker Compose. No external services.

---

## 4. Domain Model

### 4.1 Household & People

```sql
CREATE TABLE household (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    filing_status TEXT NOT NULL CHECK (filing_status IN
        ('single','mfj','mfs','hoh','qw')),
    state TEXT NOT NULL DEFAULT 'MA',
    created_at TEXT NOT NULL
);

CREATE TABLE person (
    id TEXT PRIMARY KEY,
    household_id TEXT NOT NULL REFERENCES household(id),
    name TEXT NOT NULL,
    dob TEXT NOT NULL,                          -- ISO date
    retirement_date TEXT,                       -- ISO date, nullable
    life_expectancy_age INTEGER NOT NULL,       -- e.g., 95
    is_primary INTEGER NOT NULL DEFAULT 0
);
```

### 4.2 Accounts

```sql
CREATE TABLE account (
    id TEXT PRIMARY KEY,
    household_id TEXT NOT NULL REFERENCES household(id),
    owner_person_id TEXT NOT NULL REFERENCES person(id),
    name TEXT NOT NULL,
    account_type TEXT NOT NULL CHECK (account_type IN (
        'cash','taxable_brokerage',
        'traditional_ira','traditional_401k','traditional_403b',
        'roth_ira','roth_401k',
        'hsa','governmental_457b','real_estate','debt'
    )),
    current_balance NUMERIC NOT NULL,
    expected_return NUMERIC NOT NULL,           -- annual, e.g., 0.06
    return_stddev NUMERIC,                      -- reserved for future MC, unused now
    -- Taxable brokerage
    cost_basis_pct NUMERIC,                     -- 0..1, required if taxable_brokerage
    -- Roth
    roth_first_contribution_year INTEGER,       -- required for Roth IRA/401k
    -- Governmental 457(b)
    is_governmental_457b INTEGER NOT NULL DEFAULT 0,
    has_rollover_basis_from_penalty_account INTEGER NOT NULL DEFAULT 0,
    rollover_basis_pct NUMERIC,                 -- required if has_rollover_basis... is 1
    -- HSA
    hsa_qualified_medical_expense_pct NUMERIC,  -- 0..1, default 1.0; pre-65 only meaningful
    created_at TEXT NOT NULL
);
CREATE INDEX ix_account_household ON account(household_id);
```

**Roth balance layering** is tracked per account via three balance components:

```sql
CREATE TABLE roth_basis (
    account_id TEXT PRIMARY KEY REFERENCES account(id),
    contributions_basis NUMERIC NOT NULL DEFAULT 0,   -- direct contributions, withdrawable anytime
    conversions_basis NUMERIC NOT NULL DEFAULT 0,     -- aggregate conversion basis
    earnings_balance NUMERIC NOT NULL DEFAULT 0       -- everything else (growth)
);

CREATE TABLE roth_conversion_lot (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES account(id),
    conversion_year INTEGER NOT NULL,
    converted_amount NUMERIC NOT NULL,
    -- 5-year clock starts Jan 1 of conversion_year; lot becomes penalty-free
    -- on Jan 1 of conversion_year + 5
    notes TEXT
);
CREATE INDEX ix_roth_conv_lot_account ON roth_conversion_lot(account_id);
```

### 4.3 Income & Expense Streams

```sql
CREATE TABLE income_stream (
    id TEXT PRIMARY KEY,
    household_id TEXT NOT NULL REFERENCES household(id),
    person_id TEXT REFERENCES person(id),
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN
        ('salary','pension','social_security','annuity','passive','other')),
    annual_amount NUMERIC NOT NULL,             -- in start_year dollars
    start_year INTEGER NOT NULL,
    end_year INTEGER,                           -- null = lifetime
    inflation_kind TEXT NOT NULL CHECK (inflation_kind IN
        ('cpi','ss_cola','pension_cola','none','custom')),
    custom_inflation_rate NUMERIC,              -- required if inflation_kind='custom'
    is_taxable_federal INTEGER NOT NULL DEFAULT 1,
    is_taxable_state INTEGER NOT NULL DEFAULT 1,
    -- Social Security only
    claiming_age INTEGER
);

CREATE TABLE expense_stream (
    id TEXT PRIMARY KEY,
    household_id TEXT NOT NULL REFERENCES household(id),
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN
        ('must_spend','discretionary','healthcare','one_time')),
    annual_amount NUMERIC NOT NULL,
    start_year INTEGER NOT NULL,
    end_year INTEGER,                           -- null = lifetime; for one_time, must equal start_year
    inflation_kind TEXT NOT NULL CHECK (inflation_kind IN
        ('cpi','healthcare','none','custom')),
    custom_inflation_rate NUMERIC
);
```

### 4.4 Scenarios & Assumptions

```sql
CREATE TABLE scenario (
    id TEXT PRIMARY KEY,
    household_id TEXT NOT NULL REFERENCES household(id),
    name TEXT NOT NULL,
    parent_scenario_id TEXT REFERENCES scenario(id),  -- for clone lineage
    created_at TEXT NOT NULL
);

CREATE TABLE assumption_set (
    id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL UNIQUE REFERENCES scenario(id),
    -- Inflation
    cpi_rate NUMERIC NOT NULL DEFAULT 0.025,
    healthcare_inflation_rate NUMERIC NOT NULL DEFAULT 0.04,
    ss_cola_rate NUMERIC NOT NULL DEFAULT 0.025,
    pension_cola_rate NUMERIC NOT NULL DEFAULT 0.0,
    bracket_indexing_rate NUMERIC NOT NULL DEFAULT 0.025,  -- federal & state brackets/std deduction
    -- Cash management
    cash_reserve_target_months INTEGER NOT NULL DEFAULT 24,
    -- Versioning
    irs_data_version TEXT NOT NULL DEFAULT '2024-33',
    engine_version TEXT NOT NULL,
    -- Tax election
    state TEXT NOT NULL DEFAULT 'MA',
    -- Convergence
    tax_iteration_max INTEGER NOT NULL DEFAULT 5,
    tax_iteration_tolerance NUMERIC NOT NULL DEFAULT 1.00
);

CREATE TABLE withdrawal_strategy (
    id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL UNIQUE REFERENCES scenario(id),
    order_json TEXT NOT NULL,
    -- e.g. ["cash","taxable_brokerage","traditional","roth_contrib",
    --       "roth_conversions_seasoned","hsa","roth_earnings"]
    surplus_target TEXT NOT NULL DEFAULT 'taxable_brokerage'
);
```

### 4.5 SEPP Plans

```sql
CREATE TABLE sepp_plan (
    id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL REFERENCES scenario(id),
    account_id TEXT NOT NULL REFERENCES account(id),
    method TEXT NOT NULL CHECK (method IN
        ('rmd','fixed_amortization','fixed_annuitization')),
    status TEXT NOT NULL CHECK (status IN
        ('planned','active','completed','modified','cancelled')),
    -- Dates and ages
    valuation_date TEXT NOT NULL,
    first_payment_date TEXT NOT NULL,
    required_end_date TEXT NOT NULL,            -- max(first_payment + 5y, age 59.5 date)
    age_at_first_payment NUMERIC NOT NULL,      -- decimal years
    -- Initial valuation
    account_balance_at_valuation NUMERIC NOT NULL,
    -- Interest rate (fixed methods)
    afr_prior_month NUMERIC,                    -- 120% federal mid-term, prior month
    afr_two_months_prior NUMERIC,               -- 120% federal mid-term, two months prior
    afr_month_used TEXT,                        -- 'prior' or 'two_prior'
    selected_interest_rate NUMERIC,
    max_allowed_interest_rate NUMERIC,          -- max(0.05, max(afr_prior, afr_two_prior))
    -- Calculation snapshot (locked at activation)
    initial_life_expectancy_factor NUMERIC,
    initial_annual_payment_locked NUMERIC,
    irs_notice_version TEXT NOT NULL DEFAULT 'Notice 2022-6',
    mortality_table_version TEXT,
    beneficiary_dob_snapshot TEXT,
    -- Audit
    calculation_log_json TEXT,
    -- Switch tracking
    has_switched_to_rmd INTEGER NOT NULL DEFAULT 0,
    switched_to_rmd_year INTEGER
);

CREATE UNIQUE INDEX ux_sepp_active_per_account
    ON sepp_plan(account_id) WHERE status IN ('planned','active');
```

### 4.6 Roth Conversion Schedule

```sql
CREATE TABLE roth_conversion_plan (
    id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL REFERENCES scenario(id),
    source_account_id TEXT NOT NULL REFERENCES account(id),  -- traditional
    destination_account_id TEXT NOT NULL REFERENCES account(id),  -- roth
    year INTEGER NOT NULL,
    amount NUMERIC NOT NULL,                    -- in nominal year-of-conversion dollars
    tax_payment_source_account_id TEXT REFERENCES account(id) -- default: cash
);
CREATE INDEX ix_roth_conv_plan_scenario ON roth_conversion_plan(scenario_id, year);
```

### 4.7 Projection Output

```sql
CREATE TABLE projection_run_metadata (
    id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL REFERENCES scenario(id),
    run_at TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    irs_data_version TEXT NOT NULL,
    assumption_snapshot_json TEXT NOT NULL,
    convergence_log_json TEXT                   -- per-year tax iteration counts
);

CREATE TABLE projection_year (
    id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL REFERENCES scenario(id),
    year INTEGER NOT NULL,
    age_primary INTEGER NOT NULL,
    age_spouse INTEGER,
    gross_income NUMERIC NOT NULL,
    required_distributions NUMERIC NOT NULL,    -- SEPP + RMD
    flexible_withdrawals NUMERIC NOT NULL,
    roth_conversions NUMERIC NOT NULL,
    expenses NUMERIC NOT NULL,
    federal_tax NUMERIC NOT NULL,
    state_tax NUMERIC NOT NULL,
    early_withdrawal_penalty NUMERIC NOT NULL,
    magi NUMERIC NOT NULL,
    provisional_income NUMERIC NOT NULL,
    ss_taxable_portion NUMERIC NOT NULL,
    surplus NUMERIC NOT NULL,
    ending_net_worth NUMERIC NOT NULL,
    UNIQUE(scenario_id, year)
);
CREATE INDEX ix_projection_year_scenario ON projection_year(scenario_id, year);

CREATE TABLE projection_account_balance (
    id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL REFERENCES scenario(id),
    year INTEGER NOT NULL,
    account_id TEXT NOT NULL REFERENCES account(id),
    beginning_balance NUMERIC NOT NULL,
    contributions NUMERIC NOT NULL,
    distributions NUMERIC NOT NULL,
    investment_return NUMERIC NOT NULL,
    ending_balance NUMERIC NOT NULL,
    UNIQUE(scenario_id, year, account_id)
);
CREATE INDEX ix_pab_scenario_year ON projection_account_balance(scenario_id, year);
CREATE INDEX ix_pab_account_year ON projection_account_balance(account_id, year);

CREATE TABLE projection_warning (
    id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL REFERENCES scenario(id),
    year INTEGER,
    severity TEXT NOT NULL CHECK (severity IN ('info','warning','error')),
    code TEXT NOT NULL,
    message TEXT NOT NULL
);
```

---

## 5. IRS Data Package

The `packages/irs_data/` directory contains versioned JSON files. Each file is keyed by `irs_data_version`. The default version is `'2024-33'` (IRS Internal Revenue Bulletin 2024-33).

### 5.1 Files

```
packages/irs_data/
├── 2024-33/
│   ├── manifest.json              # version, effective dates, sources
│   ├── applicable_age.json        # RMD applicable-age rules
│   ├── single_life_table.json     # used by SEPP RMD method
│   ├── uniform_lifetime_table.json # used by RMD engine
│   ├── joint_last_survivor_table.json
│   ├── afr_120_mid_term.json      # 120% AFR by year/month
│   ├── federal_brackets.json      # by year, by filing status
│   ├── ltcg_brackets.json
│   ├── standard_deduction.json
│   ├── ss_taxation_thresholds.json
│   ├── ma_state.json              # Massachusetts state tax
│   └── aca_thresholds.json        # FPL multiples for PTC cliff display
└── loader.py                      # version-aware loader, returns Decimal
```

### 5.2 Applicable Age Table

```json
[
  {"birthDateStart": "1900-01-01", "birthDateEnd": "1949-06-30", "applicableAge": 70.5, "rule": "pre-SECURE"},
  {"birthDateStart": "1949-07-01", "birthDateEnd": "1950-12-31", "applicableAge": 72,   "rule": "SECURE 1.0"},
  {"birthDateStart": "1951-01-01", "birthDateEnd": "1959-12-31", "applicableAge": 73,   "rule": "SECURE 2.0"},
  {"birthDateStart": "1960-01-01", "birthDateEnd": null,         "applicableAge": 75,   "rule": "SECURE 2.0"}
]
```

### 5.3 Loader Contract

```python
# packages/irs_data/loader.py
def load_table(name: str, version: str) -> dict | list: ...
def get_afr_120_mid_term(year: int, month: int, version: str) -> Decimal: ...
def get_single_life_factor(age: int, version: str) -> Decimal: ...
def get_uniform_lifetime_factor(age: int, version: str) -> Decimal: ...
def get_applicable_age(dob: date, version: str) -> Decimal: ...
def get_federal_brackets(year: int, filing_status: str, version: str) -> list[Bracket]: ...
def get_standard_deduction(year: int, filing_status: str, version: str) -> Decimal: ...
```

All functions return `Decimal`, never `float`. Year-keyed tables interpolate forward via `bracket_indexing_rate` for years beyond the published table.

---

## 6. SEPP Engine

Implements IRS Notice 2022-6. Pure functions in `packages/planner_engine/sepp/`.

### 6.1 Methods

1. **Required Minimum Distribution (RMD method)** — recalculated every year.
2. **Fixed Amortization** — calculated once, fixed nominal payment.
3. **Fixed Annuitization** — calculated once, fixed nominal payment. **Single-life only in MVP.**

### 6.2 Required End Date (locked)

```python
def compute_required_end_date(
    first_payment_date: date,
    dob: date,
) -> date:
    five_year_anniversary = first_payment_date + relativedelta(years=5)
    age_595_date = dob + relativedelta(years=59, months=6)
    return max(five_year_anniversary, age_595_date)
```

The 5-year rule is **5 calendar years from the date of the first distribution**, computed as exact date arithmetic via `relativedelta`. Age 59½ is computed as DOB + 59 years 6 months exactly.

### 6.3 RMD Method Recalculation

For each distribution year:
- Use **prior year-end balance** as numerator.
- Use **attained age in that year** to look up the life-expectancy factor.
- Default table: Single Life Table.
- If user elected Joint and Last Survivor Table and the designated beneficiary dies, switch to Single Life Table for that year and forward. **This switch is not a modification.**

### 6.4 Fixed Amortization

```
PMT = PV * r / (1 - (1 + r)^(-n))
```
where `PV` = `account_balance_at_valuation`, `r` = `selected_interest_rate`, `n` = life-expectancy factor for `age_at_first_payment` from the chosen table. Computed once in the first distribution year. Locked into `initial_annual_payment_locked`.

### 6.5 Fixed Annuitization

```
PMT = PV / annuity_factor(age, r, mortality_table_version)
```
Single-life only. `mortality_table_version` is locked on plan activation. ERROR if a beneficiary is designated (use fixed amortization or RMD instead).

### 6.6 Interest Rate Limit

Selected rate must not exceed:
```
max_allowed = max(0.05, max(afr_prior_month, afr_two_months_prior))
```
where the AFRs are 120% of the federal mid-term AFR for those months.

**Both candidate AFRs are stored** plus which was selected (`afr_month_used`). Validation is ERROR if `selected_interest_rate > max_allowed_interest_rate`.

### 6.7 Installment Reconciliation

If a user models monthly/quarterly installments instead of an annual payment, the sum for any calendar year must equal the annual SEPP amount within $0.01. Drift triggers ERROR (modification risk). For partial first or final years (e.g., starting August), expected sum is the prorated annual amount; same $0.01 tolerance.

### 6.8 Complete Depletion

If the SEPP account is exhausted before `required_end_date`, the final short payment is **not a modification**. Plan transitions to `status = 'completed'`. WARNING flagged to the user one or more years prior if depletion is projected.

### 6.9 One-Time Switch

- Allowed: `fixed_amortization` → `rmd`, `fixed_annuitization` → `rmd`.
- One time only. `has_switched_to_rmd` and `switched_to_rmd_year` track this.
- Blocked (ERROR): `rmd` → `fixed_*`, `fixed_*` → `fixed_*`, any second switch.

### 6.10 Governmental 457(b)

- Ordinary income tax applies to all distributions.
- 10% early-distribution penalty does **not** apply to native 457(b) basis.
- 10% penalty **does** apply to the rollover-derived portion (from a penalty-eligible plan like a 401(k)) on a **per-distribution pro-rata basis**.

```python
def split_457b_distribution(
    distribution: Decimal,
    rollover_basis_pct: Decimal,
) -> tuple[Decimal, Decimal]:
    """Returns (native_portion, rollover_portion). Penalty applies only to rollover_portion."""
    rollover = (distribution * rollover_basis_pct).quantize(Decimal("0.01"))
    native = distribution - rollover
    return native, rollover
```

### 6.11 Validation Triggered During SEPP Calculation

See §11 for the complete list. SEPP-specific validations:
- ERROR: `valuation_date > first_payment_date`
- ERROR: contribution, rollover, or transfer into SEPP account after `valuation_date` and before `required_end_date`
- ERROR: any distribution from SEPP account other than the scheduled SEPP payment before `required_end_date`
- ERROR: `selected_interest_rate > max_allowed_interest_rate`
- ERROR: second switch attempted
- ERROR: fixed annuitization with designated beneficiary
- WARNING: SEPP start age ≥ 59.5 (legal but pointless — penalty no longer applies)
- WARNING: projected depletion more than 2 years before `required_end_date`
- WARNING: fixed-method `valuation_date` outside safe window (more than ~6 months before first payment)
- INFO: taxpayer reaches RMD applicable age during active SEPP

### 6.12 Public API

```python
# packages/planner_engine/sepp/calculator.py

@dataclass(frozen=True)
class SeppCalculationInput:
    method: Literal['rmd', 'fixed_amortization', 'fixed_annuitization']
    account_balance_at_valuation: Decimal
    valuation_date: date
    first_payment_date: date
    dob: date
    beneficiary_dob: date | None
    selected_interest_rate: Decimal | None
    afr_prior_month: Decimal | None
    afr_two_months_prior: Decimal | None
    irs_data_version: str
    mortality_table_version: str | None

@dataclass(frozen=True)
class SeppCalculationResult:
    annual_payment: Decimal
    required_end_date: date
    life_expectancy_factor: Decimal
    max_allowed_interest_rate: Decimal | None
    afr_month_used: Literal['prior', 'two_prior'] | None
    audit_log: list[dict]

def calculate_initial_payment(inp: SeppCalculationInput) -> SeppCalculationResult: ...

def recalculate_rmd_method_year(
    prior_year_end_balance: Decimal,
    attained_age_this_year: int,
    use_joint_table: bool,
    beneficiary_alive: bool,
    irs_data_version: str,
) -> tuple[Decimal, dict]:  # (annual_payment, audit_entry)
    ...
```

---

## 7. Tax-Lite Engine

Pure functions in `packages/planner_engine/tax/`. Federal + Massachusetts state in MVP.

### 7.1 Federal: Computation Order

Given a year's gross flows, compute tax via:

1. **Identify income components**:
   - Ordinary income (wages, pensions, traditional distributions, SEPP, RMDs, Roth conversions, taxable annuity)
   - Long-term capital gains (taxable brokerage withdrawals, applied as `withdrawal × (1 - cost_basis_pct)`)
   - Social Security gross benefits
2. **Compute provisional income** = Ordinary income (excluding SS) + LTCG + 0.5 × SS gross + tax-exempt interest (zero in MVP).
3. **Apply simplified SS taxation**:

   | Filing Status | Tier 1 (50% taxable above) | Tier 2 (85% taxable above) |
   |---|---|---|
   | Single, HoH, QW | $25,000 | $34,000 |
   | MFJ | $32,000 | $44,000 |
   | MFS (lived together) | $0 | $0 |

   Thresholds are **not** indexed historically and are not indexed in MVP. Add a comment in code for future maintainers.

   Taxable SS = `min(0.85 × SS_gross, simplified_tier_calculation(provisional_income, status))`.

4. **AGI** = Ordinary income + LTCG + Taxable SS.
5. **MAGI** (for ACA display) = AGI + tax-exempt interest + non-taxable SS portion. In MVP, MAGI ≈ AGI + non-taxable SS portion.
6. **Taxable income** = AGI − standard deduction (year-indexed via `bracket_indexing_rate`).
7. **Federal ordinary tax**: Stack ordinary portion of taxable income through progressive brackets.
8. **LTCG tax (stacking)**: LTCG sits *on top of* ordinary taxable income. Apply LTCG brackets (0%, 15%, 20%) using ordinary taxable income as the floor. Implementation:
   ```python
   def federal_tax(
       ordinary_taxable: Decimal,
       ltcg: Decimal,
       year: int,
       filing_status: str,
       irs_data_version: str,
   ) -> Decimal:
       ord_tax = apply_ordinary_brackets(ordinary_taxable, year, filing_status, irs_data_version)
       ltcg_tax = apply_ltcg_brackets_stacked(ordinary_taxable, ltcg, year, filing_status, irs_data_version)
       return ord_tax + ltcg_tax
   ```
9. **10% early-withdrawal penalty** computed separately on penalty-eligible distributions:
   - Traditional IRA/401(k)/403(b) distributions before age 59½ that are NOT under a valid SEPP.
   - Roth earnings distributions before age 59½ + 5-year clock.
   - Roth conversion lots distributed before their per-conversion 5-year clock matures (penalty on the converted-amount portion of the distribution, applied to taxable conversions only).
   - Governmental 457(b) rollover-derived portion only, before 59½.
   - HSA non-medical distributions before age 65 (20% penalty per HSA rules; flagged as `hsa_penalty` separately).

### 7.2 Massachusetts State Tax

- Flat 5.0% on most income.
- **MA does not tax**: Social Security benefits, MA public pensions (state/municipal), federal civil-service pensions (limited).
- **MA taxes**: private pensions, IRA/401(k)/403(b) distributions (with basis recovery for previously taxed contributions — out of MVP scope; assume no MA basis), interest, dividends.
- **MA does tax** capital gains (5% short-term and long-term in MVP — MA's 12% short-term rule was repealed effective 2023; verify and set in `ma_state.json`).
- 4% surtax on income over $1M (indexed annually). Apply if AGI > threshold.
- No state-level early-withdrawal penalty.

```python
def state_tax_ma(
    taxable_income_components: TaxableIncomeMA,
    year: int,
    irs_data_version: str,
) -> Decimal: ...
```

### 7.3 Public API

```python
# packages/planner_engine/tax/engine.py

@dataclass(frozen=True)
class TaxInput:
    year: int
    filing_status: str
    state: str
    ages: dict[str, int]  # person_id -> age
    # Income components
    wages: Decimal
    pensions_taxable_federal: Decimal
    pensions_taxable_state: Decimal
    traditional_distributions: Decimal
    roth_conversions: Decimal
    sepp_distributions: Decimal
    rmd_distributions: Decimal
    annuity_taxable: Decimal
    ltcg: Decimal
    ss_gross: Decimal
    # Penalty inputs
    penalty_eligible_distributions: Decimal
    irs_data_version: str

@dataclass(frozen=True)
class TaxResult:
    federal_tax: Decimal
    state_tax: Decimal
    early_withdrawal_penalty: Decimal
    agi: Decimal
    magi: Decimal
    provisional_income: Decimal
    ss_taxable_portion: Decimal
    audit: dict

def compute_taxes(inp: TaxInput) -> TaxResult: ...
```

### 7.4 Deferred (NOT in MVP)

NIIT, AMT, full LTCG stacking edge cases, itemized deductions, QBI, IRMAA. The engine produces MAGI as output for downstream display/warnings only.

---

## 8. RMD Engine

Pure functions in `packages/planner_engine/rmd/`.

### 8.1 Applicable Age

Data-driven from `applicable_age.json`. Lookup by DOB.

### 8.2 RMD Calculation

For each year where `attained_age >= applicable_age`:
```python
rmd = prior_year_end_balance / uniform_lifetime_factor(attained_age)
```

Use **Joint and Last Survivor Table** if spouse is sole beneficiary AND spouse is more than 10 years younger than account owner. Otherwise use **Uniform Lifetime Table**.

### 8.3 RMD Account Coverage

RMDs apply to: `traditional_ira`, `traditional_401k`, `traditional_403b`, `governmental_457b`. Roth IRAs are exempt during owner's lifetime. Roth 401(k) RMDs were eliminated by SECURE 2.0 effective 2024 — exempt in this engine.

### 8.4 RMD Aggregation Rules

- IRAs (traditional): can aggregate RMDs across all IRAs and take from any one.
- 401(k)/403(b): RMD must be taken **separately from each plan**.
- 457(b): RMD must be taken from each plan separately.

The engine tracks RMD obligation per account and per aggregation group.

### 8.5 Public API

```python
def compute_rmd_for_year(
    year: int,
    accounts: list[Account],
    persons: list[Person],
    irs_data_version: str,
) -> dict[str, Decimal]:  # account_id -> required RMD
    ...
```

---

## 9. Withdrawal Engine

Pure functions in `packages/planner_engine/withdrawal/`.

### 9.1 Default Order

```json
["cash", "taxable_brokerage", "traditional", "roth_contributions", "roth_conversions_seasoned", "hsa", "roth_earnings"]
```

User-overridable via `withdrawal_strategy.order_json`.

### 9.2 SEPP Account Lockout

Accounts with an active SEPP plan are **excluded** from flexible withdrawals. They contribute their scheduled SEPP payment as required distribution income, no more.

### 9.3 Roth Three-Layer Logic

When withdrawing from a Roth account, draw in this internal order:

1. **Contributions basis** — penalty-free, tax-free, anytime.
2. **Seasoned conversion lots** — conversions whose 5-year clock has matured (`current_year >= conversion_year + 5`). Penalty-free, tax-free.
3. **Unseasoned conversion lots** — penalty applies to the taxable portion of the original conversion. Within unseasoned, draw oldest-first (FIFO) per IRS ordering rules.
4. **Earnings** — tax-free + penalty-free only if owner is ≥ 59½ AND first Roth contribution was ≥ 5 years ago (per `roth_first_contribution_year`). Otherwise both income tax and 10% penalty apply.

The engine maintains `roth_basis` and `roth_conversion_lot` records and updates them per withdrawal.

### 9.4 HSA Logic

- Distributions for qualified medical expenses: tax-free at any age.
- Pre-65 non-medical: ordinary income + 20% penalty.
- Post-65 non-medical: ordinary income, no penalty.

`hsa_qualified_medical_expense_pct` controls the assumed split.

### 9.5 Surplus Handling

After expenses, taxes, and required distributions:
1. Top up cash account to `cash_reserve_target_months × must_spend_monthly_expenses`.
2. Direct remainder to `surplus_target` (default `taxable_brokerage`).
3. If no taxable brokerage exists, the engine creates a virtual `Unassigned Taxable Savings` account at first surplus and persists it.

### 9.6 Public API

```python
def execute_withdrawals(
    target_amount: Decimal,
    accounts_state: dict[str, AccountYearState],
    order: list[str],
    year: int,
    persons: list[Person],
    sepp_locked_account_ids: set[str],
) -> WithdrawalResult: ...
```

---

## 10. Roth Conversion Engine

Pure functions in `packages/planner_engine/roth/`.

### 10.1 Conversion Mechanics

For each `roth_conversion_plan` in year Y:
1. Reduce source (traditional) account balance by `amount`.
2. Increase destination Roth `conversions_basis` by `amount` (the converted principal). Earnings remain in source until next year's growth.
3. Add new `roth_conversion_lot` with `conversion_year = Y`, `converted_amount = amount`.
4. Add `amount` to `roth_conversions` in tax engine input — taxed as ordinary income.
5. Tax payment is sourced from `tax_payment_source_account_id` (default cash). If insufficient, ERROR.

### 10.2 5-Year Clock

Clock starts **January 1 of the conversion year** (per IRS rule). Lot becomes "seasoned" on **January 1 of conversion_year + 5**. Each conversion has its own clock.

### 10.3 Validations

- ERROR: conversion source is not a traditional account.
- ERROR: conversion destination is not a Roth account.
- ERROR: conversion amount > source balance in conversion year.
- ERROR: tax payment source has insufficient funds.
- WARNING: conversion pushes MAGI across an ACA PTC cliff (display only).
- WARNING: conversion combined with other income exceeds top of current bracket by > 10% (suggest splitting).

---

## 11. Projection Engine

Pure functions in `packages/planner_engine/projection/`. The single entry point is `run_projection(scenario_id) -> ProjectionRun`.

### 11.1 Order of Operations (per year)

1. **Beginning-of-year balances** — carry from prior year ending balances.
2. **Inflate** all income/expense streams to current year's nominal dollars per inflation model.
3. **Income received** — wages, pensions, SS, annuities, passive.
4. **Required SEPP distributions** — for each active SEPP plan, take scheduled payment. RMD method recalculated; fixed methods use locked payment.
5. **Required RMDs** — compute per account, take from each.
6. **Roth conversions** — execute scheduled conversions for this year.
7. **Expenses** — sum of inflated expense streams.
8. **Initial tax estimate** — compute taxes on (income + required distributions + roth conversions + LTCG from any forced sales). Set `tax_iter = 0`.
9. **Compute funding gap** = `expenses + initial_tax_estimate - income - required_distributions`. If ≤ 0, skip to step 12.
10. **Flexible withdrawals** — withdraw `funding_gap` per withdrawal strategy, excluding SEPP-locked accounts. Apply Roth layering.
11. **Tax convergence loop**:
    ```
    while tax_iter < tax_iteration_max:
        new_tax = compute_taxes(income + required_distributions + roth_conversions + flexible_withdrawal_taxable_components)
        new_funding_gap = expenses + new_tax - income - required_distributions
        if abs(new_funding_gap - prior_funding_gap) <= tax_iteration_tolerance:
            break
        flexible_withdrawals = execute_withdrawals(new_funding_gap, ...)
        tax_iter += 1
    if tax_iter == tax_iteration_max:
        raise ConvergenceError  # logged as projection error, scenario flagged
    ```
12. **Surplus** = `income + required_distributions - expenses - final_tax`. If positive, top up cash to target, direct remainder to `surplus_target`.
13. **Apply investment returns** — end-of-year, compounded annually: `ending_pre_return * (1 + expected_return)`. Returns apply to all accounts including those that had distributions (returns computed on time-weighted average is out of MVP scope; use ending balance for simplicity, document the simplification).

    **Simplification documented:** The engine applies returns to the **ending balance after all flows**, which slightly understates returns for accounts that had distributions and slightly overstates for accounts that had contributions. For deterministic long-term projection this is acceptable; revisit when adding stochastic returns.
14. **Ending balances** — write `projection_account_balance` row per account.
15. **Year-level row** — write `projection_year` row.

### 11.2 Tax Convergence Behavior

The fixed-point iteration is required because flexible withdrawals can:
- Cross a federal ordinary bracket boundary.
- Cross an LTCG bracket boundary (0%/15%/20%).
- Push provisional income across an SS taxation tier (0%/50%/85%).
- Cross the MA $1M surtax threshold.

Tolerance is $1.00 by default. If non-convergence occurs (oscillation across a discrete tier boundary), the engine logs the divergence and selects the higher-tax solution (conservative) before proceeding.

### 11.3 SEPP Lockout During Projection

For any account where `sepp_plan.status = 'active'` in year Y:
- Excluded from flexible withdrawal pool.
- Investment returns still apply.
- No contributions allowed (would trigger modification per §6.11).
- Scheduled SEPP payment is the only outflow.

### 11.4 Public API

```python
# packages/planner_engine/projection/runner.py

@dataclass
class ProjectionRun:
    metadata: ProjectionRunMetadata
    years: list[ProjectionYear]
    account_balances: list[ProjectionAccountBalance]
    warnings: list[ProjectionWarning]

def run_projection(
    scenario: ScenarioInput,
    irs_data_version: str,
    engine_version: str,
) -> ProjectionRun: ...
```

`ScenarioInput` is a frozen dataclass containing all entities needed (accounts, persons, streams, SEPP plans, conversions, assumptions, withdrawal strategy). The engine never reads from the database directly.

---

## 12. Inflation & Returns Model

### 12.1 Inflation Streams

Each income/expense stream has an `inflation_kind`. The engine applies the appropriate rate from the assumption set:

| `inflation_kind` | Source rate |
|---|---|
| `cpi` | `cpi_rate` |
| `healthcare` | `healthcare_inflation_rate` |
| `ss_cola` | `ss_cola_rate` |
| `pension_cola` | `pension_cola_rate` |
| `none` | 0 |
| `custom` | stream's `custom_inflation_rate` |

### 12.2 Bracket / Deduction Indexing

Federal brackets, LTCG brackets, standard deduction, and the MA $1M surtax threshold are indexed forward from their published year using `bracket_indexing_rate`. SS taxation thresholds ($25k/$32k/$34k/$44k) are **not** indexed (they aren't in real life either).

### 12.3 SEPP Payments

Fixed-amortization and fixed-annuitization SEPP payments are **nominal** — not inflation-adjusted. The RMD-method SEPP payment varies year-to-year by recalculation but is also denominated in nominal dollars of that year (since it's a fraction of a nominal balance).

### 12.4 Investment Returns

Each account has `expected_return` (annual). Applied at end of year per §11.1 step 13. `return_stddev` is reserved for future Monte Carlo and ignored by the deterministic engine.

---

## 13. Validation Rules

All validations produce `projection_warning` rows. Severities: ERROR (blocks projection run), WARNING (allows run, displayed prominently), INFO (allows run, displayed in details).

### 13.1 SEPP

| Severity | Code | Condition |
|---|---|---|
| ERROR | `sepp_valuation_after_first_payment` | `valuation_date > first_payment_date` |
| ERROR | `sepp_account_contribution` | Contribution/rollover/transfer into SEPP account between `valuation_date` and `required_end_date` |
| ERROR | `sepp_account_extra_distribution` | Any non-SEPP distribution from SEPP account before `required_end_date` |
| ERROR | `sepp_installment_drift` | Sum of installments differs from annual by more than $0.01 |
| ERROR | `sepp_rate_exceeds_max` | `selected_interest_rate > max_allowed_interest_rate` |
| ERROR | `sepp_invalid_switch` | Second switch attempted, or RMD→fixed, or fixed→fixed |
| ERROR | `sepp_annuitization_with_beneficiary` | Fixed annuitization plan has designated beneficiary (MVP limitation) |
| WARNING | `sepp_pointless_age` | SEPP start age ≥ 59.5 (legal but unnecessary) |
| WARNING | `sepp_early_depletion` | Projected depletion > 2 years before `required_end_date` |
| WARNING | `sepp_valuation_window` | Fixed-method `valuation_date` more than 6 months before `first_payment_date` |
| INFO | `sepp_rmd_age_during_active` | Taxpayer reaches RMD applicable age while SEPP is active |

### 13.2 Roth Conversion

| Severity | Code | Condition |
|---|---|---|
| ERROR | `roth_conv_invalid_source` | Source is not a traditional account |
| ERROR | `roth_conv_invalid_dest` | Destination is not a Roth account |
| ERROR | `roth_conv_insufficient_source` | Amount exceeds source balance in conversion year |
| ERROR | `roth_conv_tax_payment_insufficient` | Tax payment source has insufficient funds |
| WARNING | `roth_conv_aca_cliff` | Conversion pushes MAGI across an ACA PTC threshold |
| WARNING | `roth_conv_bracket_overflow` | Conversion pushes ordinary taxable income > 10% above current bracket top |

### 13.3 Projection

| Severity | Code | Condition |
|---|---|---|
| ERROR | `projection_tax_nonconverged` | Tax fixed-point iteration did not converge within `tax_iteration_max` |
| ERROR | `projection_required_distribution_unfunded` | Required SEPP/RMD distribution exceeds account balance |
| WARNING | `projection_account_depleted` | Any account hits zero before life expectancy |
| WARNING | `projection_negative_net_worth` | Total net worth goes negative |
| WARNING | `aca_ptc_cliff_crossed` | MAGI crosses 400% FPL in any year before age 65 |
| INFO | `irmaa_threshold_crossed` | MAGI crosses IRMAA tier in any year age 63+ (IRMAA uses MAGI from 2 years prior) |

### 13.4 Account / Configuration

| Severity | Code | Condition |
|---|---|---|
| ERROR | `account_missing_cost_basis` | `taxable_brokerage` without `cost_basis_pct` |
| ERROR | `account_missing_roth_first_year` | Roth account without `roth_first_contribution_year` |
| ERROR | `account_457b_rollover_basis_inconsistent` | `has_rollover_basis_from_penalty_account=1` without `rollover_basis_pct` |
| ERROR | `assumption_irs_version_unknown` | `irs_data_version` not present in `packages/irs_data/` |

---

## 14. Frontend Specification

Next.js App Router. Tailwind. Recharts.

### 14.1 Routes

```
/                                   # Dashboard: scenario list
/household/new                      # Wizard: household + people
/scenario/[id]                      # Scenario overview
/scenario/[id]/accounts             # Account CRUD
/scenario/[id]/income               # Income stream CRUD
/scenario/[id]/expenses             # Expense stream CRUD
/scenario/[id]/sepp                 # SEPP plan CRUD + calculator preview
/scenario/[id]/roth-conversions     # Roth conversion schedule
/scenario/[id]/withdrawal           # Withdrawal strategy editor
/scenario/[id]/assumptions          # Assumption set editor
/scenario/[id]/projection           # Run + view projection
/scenario/[id]/charts               # Charts page
/scenario/compare?ids=a,b,c         # Side-by-side comparison
```

### 14.2 Required Charts (Recharts)

1. **Net Worth Over Time** — stacked area by account type.
2. **Per-Account Balances** — line per account.
3. **Cash Flow** — bar chart per year: income (green stack) vs. expenses + tax (red stack); net surplus/deficit overlay.
4. **Tax Breakdown** — stacked bar per year: federal ordinary, federal LTCG, state, early-withdrawal penalty.
5. **SEPP Payments** — line per active SEPP plan over its required period.
6. **MAGI vs. ACA Thresholds** — line of MAGI with horizontal threshold lines for 100/138/150/200/250/400% FPL (year-indexed).

### 14.3 Validation Display

- ERRORs block the "Run Projection" button until resolved.
- WARNINGs displayed in a dismissible panel above the projection.
- INFOs accessible in a "Details" expander.

### 14.4 CSV Export

Two CSVs per projection run:
- `projection_year_<scenario>_<run_at>.csv` — one row per year, all `projection_year` columns.
- `projection_account_balance_<scenario>_<run_at>.csv` — one row per (year, account).

---

## 15. Testing Plan

### 15.1 SEPP Calculator (mandatory cases)

| # | Case | Expected |
|---|---|---|
| 1 | RMD method year 1: balance 400,000, age 50, Single Life factor 36.2 | annual_payment ≈ 11,049.72 |
| 2 | Fixed amortization: balance 400,000, rate 0.04, n=36.2 | locked payment ≈ 21,108 (compute and lock to cent) |
| 3 | Fixed annuitization: IRS mortality fixture, balance 400,000, age 50, rate 0.04 | per fixture annuity factor (lock to cent) |
| 4 | Required end date: age 56 start, first payment 2025-01-15 | end = 2030-01-15 |
| 5 | Required end date: age 50 start, first payment 2025-01-15, DOB 1975-07-15 | end = 2034-12-15 + 6 months = 2035-01-15 (age 59.5 date) — verify exact date |
| 6 | Extra non-SEPP withdrawal before required end date | ERROR `sepp_account_extra_distribution` |
| 7 | Contribution to SEPP account after valuation | ERROR `sepp_account_contribution` |
| 8 | One-time switch fixed_amortization → RMD allowed | accepted; second switch blocked |
| 9 | Invalid switch RMD → fixed | ERROR `sepp_invalid_switch` |
| 10 | Complete depletion: final short payment due to exhaustion | accepted, plan status `completed` |
| 11 | Governmental 457(b), 30% rollover basis, $10k distribution at age 55 | $7k native (no penalty), $3k rollover (10% penalty = $300) |
| 12 | RMD method with joint table, beneficiary dies year 5 | switch to single life year 5+; no modification flag |
| 13 | Monthly installments starting August: 5 payments × monthly amount | sum = (5/12) × annual ± $0.01 |
| 14 | SEPP at age 60 | WARNING `sepp_pointless_age`, plan still calculates |
| 15 | Selected rate 5.5% with prior AFR 4.8%, two-prior 5.2% | ERROR `sepp_rate_exceeds_max` (max = max(5%, 5.2%) = 5.2%) |
| 16 | Selected rate 5.0% with prior AFR 4.8%, two-prior 4.9% | OK (max = max(5%, 4.9%) = 5.0%) |

### 15.2 Tax Engine (golden masters)

Hand-compute and lock 12 scenarios spanning:
- Single, MFJ, HoH filing statuses
- SS taxation tier crossings (0%, 50%, 85%)
- LTCG bracket crossings (0% → 15%, 15% → 20%)
- Federal bracket crossings
- MA $1M surtax crossing
- $0 income year (no tax)
- Roth-conversion-only year
- Year with mixed ordinary + LTCG + SS

### 15.3 RMD Engine

- DOB 1948-06-30 → applicable age 70.5
- DOB 1949-07-01 → applicable age 72
- DOB 1951-01-01 → applicable age 73
- DOB 1960-01-01 → applicable age 75
- Spouse > 10 years younger, sole beneficiary → joint table
- Multiple traditional IRAs → aggregation allowed
- Multiple 401(k)s → no aggregation; per-plan RMD

### 15.4 Withdrawal Engine

- Roth withdrawal at age 50, only contributions: tax-free, no penalty.
- Roth withdrawal at age 50 dipping into 3-year-old conversion: 10% penalty on conversion portion.
- Roth withdrawal at age 50 dipping into 6-year-old conversion: no penalty.
- Roth withdrawal at age 60, first contribution 6 years ago, dipping into earnings: tax-free, no penalty.
- Roth withdrawal at age 58, first contribution 3 years ago, earnings: ordinary income + 10% penalty on earnings portion.
- HSA non-medical at age 60: ordinary + 20% penalty.
- HSA non-medical at age 66: ordinary, no penalty.

### 15.5 Projection Engine

- 30-year deterministic scenario reproduces a hand-computed spreadsheet to the cent.
- Tax convergence: scenario engineered to oscillate across SS 85% tier converges to higher-tax side within `tax_iteration_max`.
- SEPP-locked account: zero flexible withdrawals taken from it.
- Surplus reinvestment: cash topped to target before brokerage.
- Account depletion: warning issued, projection continues, account stays at zero.

### 15.6 Property-Based Tests (Hypothesis)

- **Monotonicity**: increasing any income stream by ε with all else equal does not decrease terminal net worth.
- **Conservation**: `Σ ending_balances + Σ spent + Σ taxes = Σ beginning_balances + Σ income + Σ returns`.
- **Idempotency**: cloning a scenario and running both produces identical projections.
- **Determinism**: running the same scenario twice produces byte-identical output.

### 15.7 CI Gates

- `pytest -q` all passing.
- Coverage: 100% on `sepp/`, ≥ 90% on `planner_engine/` overall.
- AST scan: zero `float` literals or `float()` casts in `planner_engine/`.
- Type check: `mypy --strict` on `planner_engine/`, `mypy` on `apps/api/`.
- Lint: `ruff` clean.

---

## 16. Implementation Phases

Phases are sequential. Each phase has an explicit gate; the agent does not advance until the gate is green.

### Phase 1: Bootstrap

- Create monorepo structure per §3.
- Next.js app, FastAPI app, SQLite + Alembic, `planner_engine` package, `irs_data` package.
- Docker Compose with two services: `web`, `api`.
- CI pipeline: pytest, ruff, mypy, AST float scan.

**Gate:** `pytest -q` finds zero tests and exits 0. `docker-compose up` starts both services.

### Phase 2: Domain Model + Decimal Plumbing

- All SQLAlchemy models per §4.
- Custom `Money` SQLAlchemy type round-tripping `Decimal` through TEXT.
- Pydantic v2 schemas with Decimal validators.
- Alembic migration `0001_initial.py`.
- `irs_data` package with `2024-33` data files and loader.

**Gate:** Round-trip test inserts `Decimal("12345.6789")` and reads back identical. AST scan passes.

### Phase 3: SEPP Calculator

- All three methods, audit log, validation per §6.
- Pure functions, no DB or web.
- All 16 SEPP test cases passing.

**Gate:** SEPP test suite green. 100% coverage on `sepp/`.

### Phase 4: Tax-Lite Engine

- Federal: standard deduction, ordinary brackets, LTCG stacking, simplified SS taxation.
- State: Massachusetts.
- 10% early-withdrawal penalty.
- 12 golden-master tax scenarios.

**Gate:** Tax test suite green.

### Phase 5: RMD + Withdrawal + Roth Conversion Engines

- RMD engine per §8.
- Withdrawal engine with Roth 3-layer logic per §9.
- Roth conversion engine per §10.
- Test cases per §15.3, §15.4.

**Gate:** All three engine test suites green.

### Phase 6: Projection Engine

- Order of operations per §11, including tax convergence loop.
- Per-account balance writeback.
- Inflation per §12.
- Property-based tests per §15.6.

**Gate:** 30-year hand-computed scenario matches to the cent. Property tests pass.

### Phase 7: API Layer

- FastAPI endpoints for all CRUD on entities.
- `POST /scenario/{id}/run-projection` runs engine, persists output.
- `GET /scenario/{id}/projection` returns latest run.
- OpenAPI schema valid.
- API integration tests.

**Gate:** End-to-end API test creates household → scenario → accounts → runs projection → reads output.

### Phase 8: Frontend

- All routes per §14.1.
- All charts per §14.2.
- Validation display.
- CSV export.
- Playwright end-to-end test from empty DB to projection chart.

**Gate:** Playwright test passes.

### Phase 9: Test Hardening + Documentation

- Coverage targets met (§15.7).
- README with quickstart.
- In-app disclaimer (§17).

**Gate:** All CI gates green. Manual smoke test of one full retirement scenario produces sensible numbers.

### Risk Budget

Phases 3 (SEPP) and 6 (projection engine) are highest-risk: SEPP because IRS modification triggers cost real money to a user acting on the output, and projection because everything downstream depends on it. Allocate 2× the time of other phases to each. Phase 4 (tax) is medium-risk for the same compounding reason.

---

## 17. In-App Disclaimer

Display prominently on every projection view and at app first-run:

> This tool is for educational planning only. It is not tax, legal, investment, or financial advice. 72(t)/SEPP rules are strict, and improper changes can trigger penalties, recapture tax, and interest. Roth conversion strategies have multi-year tax and ACA implications. Confirm any actual retirement-account distribution or conversion plan with a qualified tax professional before acting.

---

## 18. Sources

- IRS — Substantially Equal Periodic Payments (SEPP) overview
- IRS Notice 2022-6 — SEPP methods and reasonable interest rate
- IRS — Exceptions to Tax on Early Distributions
- IRS Internal Revenue Bulletin 2024-33 — RMD Final Regulations
- IRS — Applicable Federal Rates (AFR) tables
- IRS Publication 590-B — Distributions from IRAs
- IRS Publication 575 — Pension and Annuity Income
- IRS Publication 915 — Social Security and Equivalent Railroad Retirement Benefits
- Mass.gov — Massachusetts Personal Income Tax (Schedule X, retirement income treatment)
- 26 USC §72(t), §401(a)(9), §408A

---

## 19. Glossary (Quick Reference)

- **AFR**: Applicable Federal Rate. SEPP uses 120% of mid-term AFR.
- **MAGI**: Modified Adjusted Gross Income. Used for ACA PTC eligibility, IRMAA, Roth contribution limits.
- **PIA**: Primary Insurance Amount (Social Security). Out of MVP scope.
- **PTC**: Premium Tax Credit (ACA).
- **RMD**: Required Minimum Distribution.
- **SECURE 2.0**: Setting Every Community Up for Retirement Enhancement Act 2.0 (2022). Sets RMD age at 73 (1951–1959 DOB) and 75 (1960+ DOB).
- **SEPP / 72(t)**: Substantially Equal Periodic Payments under IRC §72(t)(2)(A)(iv). Allows penalty-free early distribution.
- **WEP/GPO**: Windfall Elimination Provision / Government Pension Offset. Out of MVP scope.

---

**End of specification.** An agent implementing this document does not need to consult any prior draft. All scope decisions are explicit, all numeric defaults are pinned, all validations are enumerated.
