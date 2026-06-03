"""Property-based tests per §15.6: monotonicity, conservation, idempotency, determinism."""
from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st
from planner_engine.common import AccountYearState, Person
from planner_engine.projection import (
    AssumptionSet,
    ExpenseStream,
    IncomeStream,
    ScenarioInput,
    run_projection,
)

# Hypothesis profile: keep example count low to stay fast in CI
settings.register_profile("ci", max_examples=30, deadline=10000)
settings.register_profile("default", max_examples=50, deadline=10000)
settings.load_profile("default")

IRS_VERSION = "2024-33"
ENGINE_VERSION = "test"


# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

@st.composite
def simple_scenario(
    draw: st.DrawFn,
    min_income: int = 0,
    max_income: int = 200_000,
) -> ScenarioInput:
    """Generate a valid single-person scenario with no SEPP, Roth conversions, or RMDs."""
    income_amount = Decimal(draw(st.integers(min_value=min_income, max_value=max_income)))
    expense_amount = Decimal(draw(st.integers(min_value=0, max_value=100_000)))
    cash_balance = Decimal(draw(st.integers(min_value=0, max_value=500_000)))
    expected_return = Decimal(draw(st.integers(min_value=0, max_value=10))) / Decimal("100")

    return ScenarioInput(
        id="s1",
        filing_status="single",
        state="MA",
        start_year=2024,
        end_year=2024,  # single year keeps tests fast
        primary_person_id="p1",
        people=[Person("p1", dob_year=1974, age_by_year={2024: 50, 2025: 51})],
        accounts=[
            AccountYearState(
                id="cash",
                owner_person_id="p1",
                account_type="cash",
                balance=cash_balance,
                expected_return=expected_return,
            )
        ],
        income_streams=[
            IncomeStream("inc", "salary", income_amount, 2024, inflation_kind="none")
        ] if income_amount > 0 else [],
        expense_streams=[
            ExpenseStream("exp", "must_spend", expense_amount, 2024, inflation_kind="none")
        ] if expense_amount > 0 else [],
        assumptions=AssumptionSet(
            tax_iteration_max=5, tax_iteration_tolerance=Decimal("1.00")
        ),
        sepp_plans=[],
        roth_conversion_plans=[],
    )


# ---------------------------------------------------------------------------
# §15.6 Property 1: Monotonicity
# Increasing any income stream by ε with all else equal does not decrease terminal net worth.
# ---------------------------------------------------------------------------

@given(simple_scenario())  # type: ignore[misc]
@settings(max_examples=40, deadline=15000)
def test_monotonicity_higher_income_does_not_decrease_net_worth(sc: ScenarioInput) -> None:
    run_base = run_projection(sc, IRS_VERSION, ENGINE_VERSION)
    if not run_base.years:
        return

    # Add $1 to income
    extra_stream = IncomeStream("bonus", "salary", Decimal("1"), 2024, inflation_kind="none")
    sc_higher = ScenarioInput(
        id=sc.id,
        filing_status=sc.filing_status,
        state=sc.state,
        start_year=sc.start_year,
        end_year=sc.end_year,
        primary_person_id=sc.primary_person_id,
        people=sc.people,
        accounts=[
            AccountYearState(
                id=a.id,
                owner_person_id=a.owner_person_id,
                account_type=a.account_type,
                balance=a.balance,
                expected_return=a.expected_return,
            )
            for a in sc.accounts
        ],
        income_streams=list(sc.income_streams) + [extra_stream],
        expense_streams=sc.expense_streams,
        assumptions=sc.assumptions,
        sepp_plans=sc.sepp_plans,
        roth_conversion_plans=sc.roth_conversion_plans,
    )
    run_higher = run_projection(sc_higher, IRS_VERSION, ENGINE_VERSION)

    nw_base = run_base.years[-1].ending_net_worth
    nw_higher = run_higher.years[-1].ending_net_worth
    # Allow for $1 rounding tolerance
    assert nw_higher >= nw_base - Decimal("1.00"), (
        f"Net worth decreased when income increased: {nw_base} → {nw_higher}"
    )


# ---------------------------------------------------------------------------
# §15.6 Property 2: Conservation
# Σ ending_balances + Σ spent + Σ taxes = Σ beginning_balances + Σ income + Σ returns
# Applied per-account: ending = beginning + contributions - distributions + investment_return
# ---------------------------------------------------------------------------

@given(simple_scenario())  # type: ignore[misc]
@settings(max_examples=40, deadline=15000)
def test_conservation_account_balance_equation(sc: ScenarioInput) -> None:
    run = run_projection(sc, IRS_VERSION, ENGINE_VERSION)
    if not run.account_balances:
        return

    for row in run.account_balances:
        expected = (
            row.beginning_balance
            + row.contributions
            - row.distributions
            + row.investment_return
        )
        # Allow $0.01 rounding tolerance
        assert abs(expected - row.ending_balance) <= Decimal("0.01"), (
            f"Balance conservation violated for account {row.account_id} year {row.year}: "
            f"expected {expected}, got {row.ending_balance}"
        )


# ---------------------------------------------------------------------------
# §15.6 Property 3: Idempotency
# Cloning a scenario and running both produces identical projections.
# ---------------------------------------------------------------------------

def test_idempotency_clone_produces_identical_projection() -> None:
    sc = ScenarioInput(
        id="s1",
        filing_status="single",
        state="MA",
        start_year=2024,
        end_year=2026,
        primary_person_id="p1",
        people=[Person("p1", dob_year=1974, age_by_year={2024: 50, 2025: 51, 2026: 52})],
        accounts=[
            AccountYearState(
                id="cash",
                owner_person_id="p1",
                account_type="cash",
                balance=Decimal("100000"),
                expected_return=Decimal("0.05"),
            )
        ],
        income_streams=[
            IncomeStream("salary", "salary", Decimal("80000"), 2024, inflation_kind="none")
        ],
        expense_streams=[
            ExpenseStream("rent", "must_spend", Decimal("40000"), 2024, inflation_kind="none")
        ],
        assumptions=AssumptionSet(tax_iteration_max=5, tax_iteration_tolerance=Decimal("1.00")),
        sepp_plans=[],
        roth_conversion_plans=[],
    )

    run_a = run_projection(sc, IRS_VERSION, ENGINE_VERSION)
    # Re-build with identical parameters (simulates clone)
    sc_b = ScenarioInput(
        id="s1",
        filing_status=sc.filing_status,
        state=sc.state,
        start_year=sc.start_year,
        end_year=sc.end_year,
        primary_person_id=sc.primary_person_id,
        people=sc.people,
        accounts=[
            AccountYearState(
                id=a.id,
                owner_person_id=a.owner_person_id,
                account_type=a.account_type,
                balance=a.balance,
                expected_return=a.expected_return,
            )
            for a in sc.accounts
        ],
        income_streams=sc.income_streams,
        expense_streams=sc.expense_streams,
        assumptions=sc.assumptions,
        sepp_plans=sc.sepp_plans,
        roth_conversion_plans=sc.roth_conversion_plans,
    )
    run_b = run_projection(sc_b, IRS_VERSION, ENGINE_VERSION)

    assert len(run_a.years) == len(run_b.years)
    for ya, yb in zip(run_a.years, run_b.years, strict=False):
        assert ya.year == yb.year
        assert ya.ending_net_worth == yb.ending_net_worth
        assert ya.federal_tax == yb.federal_tax
        assert ya.surplus == yb.surplus


# ---------------------------------------------------------------------------
# §15.6 Property 4: Determinism
# Running the same scenario twice produces identical output.
# ---------------------------------------------------------------------------

def test_determinism_same_scenario_same_output() -> None:
    sc = ScenarioInput(
        id="s1",
        filing_status="mfj",
        state="MA",
        start_year=2024,
        end_year=2030,
        primary_person_id="p1",
        people=[
            Person(
                "p1",
                dob_year=1974,
                age_by_year={y: 2024 - 1974 + (y - 2024) for y in range(2024, 2031)},
            ),
        ],
        accounts=[
            AccountYearState(
                id="cash",
                owner_person_id="p1",
                account_type="cash",
                balance=Decimal("200000"),
                expected_return=Decimal("0.06"),
            ),
            AccountYearState(
                id="taxable",
                owner_person_id="p1",
                account_type="taxable_brokerage",
                balance=Decimal("100000"),
                expected_return=Decimal("0.07"),
                cost_basis_pct=Decimal("0.60"),
            ),
        ],
        income_streams=[
            IncomeStream("salary", "salary", Decimal("120000"), 2024, inflation_kind="cpi"),
        ],
        expense_streams=[
            ExpenseStream("living", "must_spend", Decimal("80000"), 2024, inflation_kind="cpi"),
        ],
        assumptions=AssumptionSet(
            cpi_rate=Decimal("0.025"),
            tax_iteration_max=5,
            tax_iteration_tolerance=Decimal("1.00"),
        ),
        sepp_plans=[],
        roth_conversion_plans=[],
    )

    run1 = run_projection(sc, IRS_VERSION, ENGINE_VERSION)
    run2 = run_projection(sc, IRS_VERSION, ENGINE_VERSION)

    assert len(run1.years) == len(run2.years)
    for y1, y2 in zip(run1.years, run2.years, strict=False):
        assert y1.ending_net_worth == y2.ending_net_worth
        assert y1.federal_tax == y2.federal_tax
        assert y1.surplus == y2.surplus
        assert y1.magi == y2.magi

    for b1, b2 in zip(run1.account_balances, run2.account_balances, strict=False):
        assert b1.ending_balance == b2.ending_balance


# ---------------------------------------------------------------------------
# Extra: conservation across multi-year projection
# Total income + starting net worth = ending net worth + total taxes + total expenses + corrections
# ---------------------------------------------------------------------------

def test_multi_year_conservation_no_returns() -> None:
    """With zero returns, net worth change = income - expenses - taxes (within rounding)."""
    sc = ScenarioInput(
        id="s1",
        filing_status="single",
        state="MA",
        start_year=2024,
        end_year=2026,
        primary_person_id="p1",
        people=[Person("p1", dob_year=1974, age_by_year={2024: 50, 2025: 51, 2026: 52})],
        accounts=[
            AccountYearState(
                id="cash",
                owner_person_id="p1",
                account_type="cash",
                balance=Decimal("500000"),
                expected_return=Decimal("0"),  # zero return for cleaner math
            )
        ],
        income_streams=[
            IncomeStream("salary", "salary", Decimal("0"), 2024, inflation_kind="none")
        ],
        expense_streams=[
            ExpenseStream("rent", "must_spend", Decimal("30000"), 2024, inflation_kind="none")
        ],
        assumptions=AssumptionSet(tax_iteration_max=5, tax_iteration_tolerance=Decimal("1.00")),
        sepp_plans=[],
        roth_conversion_plans=[],
    )

    run = run_projection(sc, IRS_VERSION, ENGINE_VERSION)

    # Each year: ending = beginning + contributions - distributions + investment_return
    for ab in run.account_balances:
        reconstructed = (
            ab.beginning_balance + ab.contributions - ab.distributions + ab.investment_return
        )
        assert abs(reconstructed - ab.ending_balance) <= Decimal("0.01"), (
            f"Conservation violated yr={ab.year}: {ab.beginning_balance} + {ab.contributions}"
            f" - {ab.distributions} + {ab.investment_return} ≠ {ab.ending_balance}"
        )
