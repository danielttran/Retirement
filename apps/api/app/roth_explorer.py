"""Roth Conversion Explorer (Boldin-style).

Given a built plan, suggest a year-by-year Roth-conversion schedule under a chosen rule:

* ``bracket`` — convert traditional balances up to the top of a target federal tax bracket each year
  (e.g. fill the 24% bracket), the classic "bracket-fill" strategy.
* ``irmaa`` — convert up to just under a chosen MAGI ceiling to avoid an IRMAA tier.

The explorer runs the deterministic engine for a baseline, derives per-year headroom, then runs a
projected scenario with the suggested conversions injected so the user can compare lifetime tax and
estate value before applying anything.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from irs_data import get_federal_brackets
from planner_engine.projection import ScenarioInput, run_projection
from planner_engine.roth import RothConversionPlan as EngineRothConversionPlan

ZERO = Decimal("0")
_TRADITIONAL_TYPES = {"traditional_ira", "traditional_401k", "traditional_403b"}
_ROTH_TYPES = {"roth_ira", "roth_401k"}


@dataclass(frozen=True)
class ConversionSuggestion:
    year: int
    amount: Decimal
    ordinary_taxable_income: Decimal
    magi: Decimal
    headroom: Decimal
    traditional_balance: Decimal


@dataclass(frozen=True)
class ExplorerResult:
    strategy: str
    source_account_id: str | None
    destination_account_id: str | None
    suggestions: list[ConversionSuggestion]
    total_converted: Decimal
    baseline_lifetime_tax: Decimal
    projected_lifetime_tax: Decimal
    baseline_estate: Decimal
    projected_estate: Decimal
    note: str | None = None


def _bracket_ceiling(year: int, filing_status: str, target_rate: Decimal, version: str) -> Decimal:
    """Top of the bracket whose marginal rate equals ``target_rate`` (in that year's dollars)."""
    best: Decimal | None = None
    for bracket in get_federal_brackets(year, filing_status, version):
        if bracket.rate <= target_rate and bracket.ceiling is not None:
            best = bracket.ceiling
    return best if best is not None else ZERO


def suggest_roth_conversions(
    scenario: ScenarioInput,
    irs_data_version: str,
    engine_version: str,
    strategy: str,
    target_rate: Decimal,
    irmaa_magi_ceiling: Decimal,
    start_year: int,
    end_year: int,
) -> ExplorerResult:
    source = next((a for a in scenario.accounts if a.account_type in _TRADITIONAL_TYPES), None)
    dest = next((a for a in scenario.accounts if a.account_type in _ROTH_TYPES), None)
    baseline = run_projection(scenario, irs_data_version, engine_version)
    baseline_summary = baseline.summary

    if source is None or dest is None:
        return ExplorerResult(
            strategy=strategy,
            source_account_id=source.id if source else None,
            destination_account_id=dest.id if dest else None,
            suggestions=[],
            total_converted=ZERO,
            baseline_lifetime_tax=baseline_summary.lifetime_total_tax,
            projected_lifetime_tax=baseline_summary.lifetime_total_tax,
            baseline_estate=baseline_summary.estate_net_worth,
            projected_estate=baseline_summary.estate_net_worth,
            note="Need at least one traditional account and one Roth account to convert.",
        )

    # Per-year baseline tax position + available traditional balance in the source account.
    year_rows = {row.year: row for row in baseline.years}
    source_balance = {
        bal.year: bal.ending_balance
        for bal in baseline.account_balances
        if bal.account_id == source.id
    }

    def build(strat: str, rate: Decimal) -> list[ConversionSuggestion]:
        out: list[ConversionSuggestion] = []
        for year in range(start_year, end_year + 1):
            row = year_rows.get(year)
            if row is None:
                continue
            available = source_balance.get(year, ZERO)
            if available <= ZERO:
                continue
            if strat == "irmaa":
                headroom = irmaa_magi_ceiling - row.magi
            else:
                ceiling = _bracket_ceiling(year, scenario.filing_status, rate, irs_data_version)
                headroom = ceiling - row.ordinary_taxable_income
            amount = min(max(ZERO, headroom), available).quantize(Decimal("1"))
            if amount <= ZERO:
                continue
            out.append(
                ConversionSuggestion(
                    year=year,
                    amount=amount,
                    ordinary_taxable_income=row.ordinary_taxable_income,
                    magi=row.magi,
                    headroom=max(ZERO, headroom),
                    traditional_balance=available,
                )
            )
        return out

    def project(suggestions: list[ConversionSuggestion]) -> tuple[Decimal, Decimal]:
        plans = list(scenario.roth_conversion_plans) + [
            EngineRothConversionPlan(
                source_account_id=source.id,
                destination_account_id=dest.id,
                year=s.year,
                amount=s.amount,
            )
            for s in suggestions
        ]
        run = run_projection(
            replace(scenario, roth_conversion_plans=plans), irs_data_version, engine_version
        )
        return run.summary.lifetime_total_tax, run.summary.estate_net_worth

    goal_strategies = {"highest_estate", "lowest_lifetime_tax"}
    if strategy in goal_strategies:
        # Search candidate brackets and pick the one that best meets the goal.
        candidates = [Decimal(r) for r in ("0.10", "0.12", "0.22", "0.24", "0.32")]
        # Seed with the "no conversion" baseline so the optimizer never recommends a worse plan.
        best: tuple[list[ConversionSuggestion], Decimal, Decimal] = (
            [],
            baseline_summary.lifetime_total_tax,
            baseline_summary.estate_net_worth,
        )
        for rate in candidates:
            sug = build("bracket", rate)
            if not sug:
                continue
            tax, estate = project(sug)
            if strategy == "highest_estate" and estate > best[2]:
                best = (sug, tax, estate)
            elif strategy == "lowest_lifetime_tax" and tax < best[1]:
                best = (sug, tax, estate)
        suggestions, proj_tax, proj_estate = best
    else:
        suggestions = build(strategy, target_rate)
        proj_tax, proj_estate = project(suggestions)

    return ExplorerResult(
        strategy=strategy,
        source_account_id=source.id,
        destination_account_id=dest.id,
        suggestions=suggestions,
        total_converted=sum((s.amount for s in suggestions), ZERO),
        baseline_lifetime_tax=baseline_summary.lifetime_total_tax,
        projected_lifetime_tax=proj_tax,
        baseline_estate=baseline_summary.estate_net_worth,
        projected_estate=proj_estate,
    )
