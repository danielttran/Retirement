from __future__ import annotations

from decimal import Decimal

from planner_engine.common import AccountYearState, Person
from planner_engine.projection import (
    AssumptionSet,
    ExpenseStream,
    IncomeStream,
    ScenarioInput,
    SeppProjectionPlan,
    run_projection,
)
from planner_engine.roth import RothConversionPlan


def person(pid: str, age: int, year: int = 2024) -> Person:
    return Person(id=pid, dob_year=year - age, age_by_year={year: age, year + 1: age + 1})


def account(
    account_id: str,
    account_type: str,
    balance: str,
    owner: str = "p1",
    expected_return: str = "0",
) -> AccountYearState:
    return AccountYearState(
        id=account_id,
        owner_person_id=owner,
        account_type=account_type,
        balance=Decimal(balance),
        expected_return=Decimal(expected_return),
    )


def scenario(
    accounts: list[AccountYearState],
    people: list[Person] | None = None,
    income_streams: list[IncomeStream] | None = None,
    expense_streams: list[ExpenseStream] | None = None,
    sepp_plans: list[SeppProjectionPlan] | None = None,
    roth_conversion_plans: list[RothConversionPlan] | None = None,
    end_year: int = 2024,
) -> ScenarioInput:
    return ScenarioInput(
        id="s1",
        filing_status="single",
        state="MA",
        start_year=2024,
        end_year=end_year,
        primary_person_id="p1",
        people=people or [person("p1", 55)],
        accounts=accounts,
        income_streams=income_streams or [],
        expense_streams=expense_streams or [],
        assumptions=AssumptionSet(tax_iteration_max=5, tax_iteration_tolerance=Decimal("1.00")),
        sepp_plans=sepp_plans or [],
        roth_conversion_plans=roth_conversion_plans or [],
    )


def test_projection_withdraws_cash_for_basic_funding_gap() -> None:
    run = run_projection(
        scenario(
            [account("cash", "cash", "50000")],
            expense_streams=[
                ExpenseStream("rent", "must_spend", Decimal("10000"), 2024, inflation_kind="none")
            ],
        ),
        "2024-33",
        "test",
    )

    year = run.years[0]
    assert year.flexible_withdrawals == Decimal("10000.00")
    assert year.federal_tax == Decimal("0.00")
    assert year.ending_net_worth == Decimal("40000.00")
    assert run.account_balances[0].distributions == Decimal("10000.00")


def test_projection_surplus_tops_up_cash_reserve_then_taxable_target() -> None:
    taxable = account("taxable", "taxable_brokerage", "0")
    run = run_projection(
        scenario(
            [account("cash", "cash", "1000"), taxable],
            income_streams=[
                IncomeStream("salary", "salary", Decimal("50000"), 2024, inflation_kind="none")
            ],
            expense_streams=[
                ExpenseStream("rent", "must_spend", Decimal("10000"), 2024, inflation_kind="none")
            ],
        ),
        "2024-33",
        "test",
    )

    balances = {row.account_id: row for row in run.account_balances}
    assert run.years[0].surplus > Decimal("0")
    assert balances["cash"].contributions == Decimal("19000.00")
    assert balances["taxable"].contributions > Decimal("0")


def test_projection_takes_rmd_and_records_required_distribution() -> None:
    owner = Person("p1", dob_year=1951, age_by_year={2024: 73})
    run = run_projection(
        scenario(
            [account("ira", "traditional_ira", "265000"), account("cash", "cash", "0")],
            people=[owner],
        ),
        "2024-33",
        "test",
    )

    year = run.years[0]
    assert year.required_distributions == Decimal("10000.00")
    ira_balance = next(row for row in run.account_balances if row.account_id == "ira")
    assert ira_balance.distributions == Decimal("10000.00")


def test_projection_executes_roth_conversion_and_funds_tax_gap() -> None:
    traditional = account("trad", "traditional_ira", "50000")
    roth = account("roth", "roth_ira", "0")
    cash = account("cash", "cash", "10000")
    run = run_projection(
        scenario(
            [traditional, roth, cash],
            roth_conversion_plans=[
                RothConversionPlan("trad", "roth", 2024, Decimal("10000")),
            ],
        ),
        "2024-33",
        "test",
    )

    balances = {row.account_id: row for row in run.account_balances}
    assert run.years[0].roth_conversions == Decimal("10000.00")
    assert run.years[0].flexible_withdrawals > Decimal("0")
    assert balances["trad"].ending_balance == Decimal("40000.00")
    assert balances["roth"].ending_balance == Decimal("10000.00")
    assert balances["cash"].ending_balance < Decimal("10000.00")


# ---------------------------------------------------------------------------
# _active_sepp_account_ids — boundary tests on start_year / required_end_year.
# ---------------------------------------------------------------------------


def _make_sepp_plan(
    plan_id: str = "sepp",
    account_id: str = "ira",
    status: str = "active",
    start_year: int = 2024,
    required_end_year: int = 2029,
    annual_payment: str = "1000",
) -> SeppProjectionPlan:
    return SeppProjectionPlan(
        plan_id,
        account_id,
        "fixed_amortization",
        status,
        start_year,
        required_end_year,
        Decimal(annual_payment),
    )


def test_active_sepp_account_ids_excludes_year_before_start() -> None:
    from planner_engine.projection.runner import _active_sepp_account_ids

    plans = [_make_sepp_plan(start_year=2025, required_end_year=2030)]
    assert _active_sepp_account_ids(plans, 2024) == set()


def test_active_sepp_account_ids_excludes_year_after_end() -> None:
    from planner_engine.projection.runner import _active_sepp_account_ids

    plans = [_make_sepp_plan(start_year=2020, required_end_year=2024)]
    assert _active_sepp_account_ids(plans, 2025) == set()


def test_active_sepp_account_ids_includes_exact_start_year() -> None:
    from planner_engine.projection.runner import _active_sepp_account_ids

    plans = [_make_sepp_plan(start_year=2025, required_end_year=2030)]
    assert _active_sepp_account_ids(plans, 2025) == {"ira"}


def test_active_sepp_account_ids_includes_exact_required_end_year() -> None:
    from planner_engine.projection.runner import _active_sepp_account_ids

    plans = [_make_sepp_plan(start_year=2020, required_end_year=2025)]
    assert _active_sepp_account_ids(plans, 2025) == {"ira"}


def test_active_sepp_account_ids_excludes_planned_status() -> None:
    from planner_engine.projection.runner import _active_sepp_account_ids

    plans = [_make_sepp_plan(status="planned", start_year=2020, required_end_year=2030)]
    assert _active_sepp_account_ids(plans, 2024) == set()


# ---------------------------------------------------------------------------
# _take_sepp_distributions — payment vs. balance and credit against spending gap.
# ---------------------------------------------------------------------------


def test_take_sepp_distributions_uses_min_of_balance_and_payment() -> None:
    """SEPP plan with $1000 payment but only $400 in account → distributes $400."""
    ira = account("ira", "traditional_ira", "400")
    cash = account("cash", "cash", "0")
    run = run_projection(
        scenario(
            [ira, cash],
            sepp_plans=[_make_sepp_plan(annual_payment="1000")],
        ),
        "2024-33",
        "test",
    )
    balances = {row.account_id: row for row in run.account_balances}
    assert balances["ira"].distributions == Decimal("400.00")
    assert run.years[0].required_distributions == Decimal("400.00")


def test_sepp_distribution_credits_spending_gap_no_flex_needed() -> None:
    """SEPP $16k/yr fully covers $2k must_spend → no flex withdrawals, no funding gap."""
    ira = account("ira", "traditional_ira", "300000")
    cash = account("cash", "cash", "100")
    run = run_projection(
        scenario(
            [ira, cash],
            expense_streams=[
                ExpenseStream("rent", "must_spend", Decimal("2000"), 2024, inflation_kind="none")
            ],
            sepp_plans=[_make_sepp_plan(annual_payment="16000")],
        ),
        "2024-33",
        "test",
    )
    year = run.years[0]
    assert year.required_distributions == Decimal("16000.00")
    assert year.flexible_withdrawals == Decimal("0.00")
    funding_gap_codes = {w.code for w in run.warnings}
    assert "projection_funding_gap_unfunded" not in funding_gap_codes


def test_sepp_shortfall_covered_by_other_accounts() -> None:
    """SEPP $1k, must_spend $5k → flex withdraws ≈ $4k from cash."""
    ira = account("ira", "traditional_ira", "100000")
    cash = account("cash", "cash", "50000")
    run = run_projection(
        scenario(
            [ira, cash],
            expense_streams=[
                ExpenseStream("rent", "must_spend", Decimal("5000"), 2024, inflation_kind="none")
            ],
            sepp_plans=[_make_sepp_plan(annual_payment="1000")],
        ),
        "2024-33",
        "test",
    )
    year = run.years[0]
    assert year.required_distributions == Decimal("1000.00")
    # gap ≈ $5k expenses - $1k SEPP = $4k (small state tax adds a bit on the $1k ordinary).
    assert year.flexible_withdrawals >= Decimal("4000.00")
    assert year.flexible_withdrawals < Decimal("4500.00")
    funding_gap_codes = {w.code for w in run.warnings}
    assert "projection_funding_gap_unfunded" not in funding_gap_codes


def test_sepp_account_balance_untouched_by_flex_when_only_other_account_is_cash() -> None:
    """SEPP-locked account isn't touched by flex; cash funds the gap."""
    ira = account("ira", "traditional_ira", "100000")
    cash = account("cash", "cash", "50000")
    run = run_projection(
        scenario(
            [ira, cash],
            expense_streams=[
                ExpenseStream("rent", "must_spend", Decimal("3000"), 2024, inflation_kind="none")
            ],
            sepp_plans=[_make_sepp_plan(annual_payment="500")],
        ),
        "2024-33",
        "test",
    )
    balances = {row.account_id: row for row in run.account_balances}
    # IRA distributions == only the SEPP amount, no extra flex withdrawals
    assert balances["ira"].distributions == Decimal("500.00")
    # Cash funded the rest of the spending gap (gap ≈ $2.5k + small state tax on SEPP).
    assert balances["cash"].distributions >= Decimal("2500.00")
    assert balances["cash"].distributions < Decimal("2700.00")


def test_planned_sepp_plan_takes_no_distributions() -> None:
    """SEPP plan with status=planned → engine ignores it; balance untouched."""
    ira = account("ira", "traditional_ira", "100000")
    cash = account("cash", "cash", "10000")
    run = run_projection(
        scenario(
            [ira, cash],
            sepp_plans=[_make_sepp_plan(status="planned", annual_payment="5000")],
        ),
        "2024-33",
        "test",
    )
    balances = {row.account_id: row for row in run.account_balances}
    assert run.years[0].required_distributions == Decimal("0.00")
    assert balances["ira"].distributions == Decimal("0.00")


def test_projection_excludes_active_sepp_account_from_flexible_withdrawals() -> None:
    ira = account("ira", "traditional_ira", "50000")
    cash = account("cash", "cash", "2000")
    run = run_projection(
        scenario(
            [ira, cash],
            expense_streams=[
                ExpenseStream("rent", "must_spend", Decimal("5000"), 2024, inflation_kind="none")
            ],
            sepp_plans=[
                SeppProjectionPlan(
                    "sepp",
                    "ira",
                    "fixed_amortization",
                    "active",
                    2024,
                    2029,
                    Decimal("1000"),
                )
            ],
        ),
        "2024-33",
        "test",
    )

    balances = {row.account_id: row for row in run.account_balances}
    assert run.years[0].required_distributions == Decimal("1000.00")
    assert run.years[0].flexible_withdrawals == Decimal("2000.00")
    assert balances["ira"].distributions == Decimal("1000.00")
    assert balances["cash"].distributions == Decimal("2000.00")
    assert {warning.code for warning in run.warnings} == {"projection_funding_gap_unfunded"}
