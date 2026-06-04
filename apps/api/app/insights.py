"""Financial Wellness Score + Coach insights (Boldin-style).

Derives a 0-100 wellness score from a deterministic projection plus a Monte Carlo chance-of-success,
and emits actionable, rule-based coach alerts. Lives outside the pure engine so it can orchestrate
the projection + Monte Carlo together.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from planner_engine.projection import ProjectionRun, ScenarioInput

from app.montecarlo import MonteCarloResult

ZERO = Decimal("0")
_TRADITIONAL_TYPES = {
    "traditional_ira",
    "traditional_401k",
    "traditional_403b",
    "governmental_457b",
}


@dataclass(frozen=True)
class ScoreComponent:
    label: str
    score: int
    weight: int
    detail: str


@dataclass(frozen=True)
class Alert:
    severity: str  # "success" | "info" | "warning" | "critical"
    title: str
    message: str


@dataclass(frozen=True)
class InsightsResult:
    score: int
    rating: str
    components: list[ScoreComponent]
    alerts: list[Alert]


def _rating(score: int) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Fair"
    return "At Risk"


def compute_insights(
    scenario: ScenarioInput,
    run: ProjectionRun,
    monte_carlo: MonteCarloResult,
    life_expectancy_age: int,
) -> InsightsResult:
    summary = run.summary
    components: list[ScoreComponent] = []
    alerts: list[Alert] = []

    # 1. Chance of success (Monte Carlo) — weight 45.
    chance = int(monte_carlo.chance_of_success)
    components.append(
        ScoreComponent(
            "Chance of success",
            chance,
            45,
            f"{monte_carlo.chance_of_success}% of simulations never run out of money.",
        )
    )
    if chance >= 90:
        alerts.append(
            Alert("success", "Strong plan", f"{chance}% Monte Carlo chance of success.")
        )
    elif chance < 70:
        alerts.append(
            Alert(
                "warning",
                "Plan needs attention",
                f"Only a {chance}% chance of success. Consider spending less, saving more, "
                "working longer, or delaying Social Security.",
            )
        )

    # 2. Savings longevity — weight 30.
    if summary.out_of_savings_age is None:
        longevity_score = 100
        longevity_detail = "Liquid savings last through your full life expectancy."
    else:
        gap = max(0, life_expectancy_age - summary.out_of_savings_age)
        horizon = max(1, life_expectancy_age - run.years[0].age_primary)
        longevity_score = max(0, 100 - int(gap * 100 / horizon))
        longevity_detail = (
            f"Liquid savings run out at age {summary.out_of_savings_age}, "
            f"before life expectancy {life_expectancy_age}."
        )
        alerts.append(
            Alert(
                "critical" if gap > 5 else "warning",
                "Savings shortfall",
                longevity_detail + " Reduce spending or increase income to close the gap.",
            )
        )
    components.append(
        ScoreComponent("Savings longevity", longevity_score, 30, longevity_detail)
    )

    # 3. Tax efficiency — weight 15 (lower lifetime tax / income is better).
    income = summary.total_lifetime_income
    tax_ratio = (summary.lifetime_total_tax / income) if income > ZERO else ZERO
    tax_score = max(0, 100 - int(tax_ratio * Decimal("400")))  # 25% effective → 0
    components.append(
        ScoreComponent(
            "Tax efficiency",
            tax_score,
            15,
            f"Lifetime taxes are {formatpct(tax_ratio)} of lifetime income "
            f"({money(summary.lifetime_total_tax)}).",
        )
    )

    # 4. Estate / legacy — weight 10.
    estate_score = 100 if summary.estate_net_worth > ZERO else 0
    components.append(
        ScoreComponent(
            "Estate",
            estate_score,
            10,
            f"Projected estate at age {summary.final_age}: {money(summary.estate_net_worth)}.",
        )
    )

    total_weight = sum(c.weight for c in components)
    score = int(sum(c.score * c.weight for c in components) / total_weight) if total_weight else 0

    _rule_based_alerts(scenario, run, alerts)

    return InsightsResult(score=score, rating=_rating(score), components=components, alerts=alerts)


def _rule_based_alerts(scenario: ScenarioInput, run: ProjectionRun, alerts: list[Alert]) -> None:
    summary = run.summary

    if summary.total_lifetime_irmaa > ZERO:
        alerts.append(
            Alert(
                "info",
                "Medicare IRMAA surcharges",
                f"You pay {money(summary.total_lifetime_irmaa)} in lifetime IRMAA surcharges. "
                "Managing MAGI (e.g., Roth conversions before 63) can reduce this.",
            )
        )

    if any(y.ending_net_worth < ZERO for y in run.years):
        alerts.append(
            Alert("critical", "Negative net worth", "Net worth goes negative in some years.")
        )

    # Roth conversion opportunity: sizeable traditional balances heading into RMDs.
    trad_ids = {a.id for a in scenario.accounts if a.account_type in _TRADITIONAL_TYPES}
    if trad_ids and summary.total_lifetime_roth_conversions == ZERO:
        first_year = run.years[0].year if run.years else 0
        trad_balance = sum(
            (
                b.ending_balance
                for b in run.account_balances
                if b.account_id in trad_ids and b.year == first_year
            ),
            ZERO,
        )
        if trad_balance > Decimal("250000"):
            alerts.append(
                Alert(
                    "info",
                    "Roth conversion opportunity",
                    f"You hold {money(trad_balance)} in pre-tax accounts and have no conversions "
                    "planned. The Roth Conversion Explorer can estimate lifetime-tax savings.",
                )
            )

    # Working income but no contributions modeled.
    has_salary = any(s.kind == "salary" for s in scenario.income_streams)
    if has_salary and not scenario.contribution_plans:
        alerts.append(
            Alert(
                "info",
                "Add retirement contributions",
                "You have earned income but no contributions modeled. Add 401(k)/IRA/HSA "
                "contributions (with any employer match) to model the accumulation phase.",
            )
        )


def money(value: Decimal) -> str:
    return f"${value:,.0f}"


def formatpct(ratio: Decimal) -> str:
    return f"{ratio * Decimal('100'):.1f}%"
